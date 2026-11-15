"""
vault_watcher.py
Records edits made outside Loci (Obsidian, a text editor, a sync tool) soon after
they happen, instead of at the next Loci write.

It runs in the `loci` UI server process only. The MCP server is a separate
process and does not start it; there the history still catches such edits at the
next write.

How it works
  - `watchdog` reports file events. Events that arrive close together are one
    burst: when nothing new arrives for QUIET_SECONDS, the files of the burst are
    recorded as one commit.
  - A timer scan of the whole vault runs every SCAN_SECONDS. It covers folders
    that give no native events (some network and synced folders) and any event
    the platform dropped.
  - A burst is recorded under the vault write lock, so it never lands inside a
    Loci write. Loci's own writes are already committed when the burst is
    recorded, so they add no commit and cost only a stat of the file.
  - When a burst produced a commit, the graph is rebuilt on the next read, so a
    note added, deleted or edited by hand shows in the app without a restart.

Operating systems
  `watchdog` picks the native backend itself: FSEvents on macOS, inotify on
  Linux, ReadDirectoryChangesW on Windows. Nothing here branches on the OS, and
  the timer scan is plain Python. What still differs, and is not handled here:
  - Linux: inotify has a per-user watch limit (fs.inotify.max_user_watches). A
    very large vault can exceed it; the observer then fails to start and the
    timer scan alone runs (a warning is logged).
  - Windows: not a tested platform. vault_history.write_lock uses fcntl, which
    Windows lacks, so a burst there is not serialised with a Loci write. That
    needs a cross-platform lock in its own PR.
  - Network and synced folders may give no events on any OS: the timer scan.

The watcher never raises into the server. When `watchdog` cannot start, the
timer scan alone keeps working.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from loci.tools import nx_graph, vault_history

log = logging.getLogger(__name__)

QUIET_SECONDS = 2.0      # no event for this long ends a burst
SCAN_SECONDS = 45.0      # whole-vault scan, in case an event was missed
_POLL_SECONDS = 0.25     # how often the worker looks at the clock


class VaultWatcher:
    def __init__(
        self,
        vault_root: Path,
        *,
        quiet: float = QUIET_SECONDS,
        scan_every: float = SCAN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        on_recorded: Optional[Callable[[str], None]] = None,
    ):
        self.vault_root = Path(vault_root)
        self.quiet = quiet
        self.scan_every = scan_every
        self._clock = clock
        self._on_recorded = on_recorded or self._invalidate_graph
        self._lock = threading.Lock()
        self._paths: set[str] = set()
        self._everything = False        # a folder event: compare the whole vault
        self._last_event = 0.0
        self._last_scan = clock()
        self._observer = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # -- input -------------------------------------------------------------

    def _records(self, *paths: str) -> bool:
        """True when history records at least one of these paths."""
        return any(vault_history._relative(self.vault_root, [p]) for p in paths)

    def note(self, *paths: str, everything: bool = False) -> None:
        """Remember that these files changed. Files history never records (the
        store itself, editor folders, swap files) are ignored, so Loci's own
        writes to `.loci/` do not keep a burst open."""
        keep = {p for p in paths if p and self._records(p)}
        if not keep and not everything:
            return
        with self._lock:
            self._paths |= keep
            self._everything = self._everything or everything
            self._last_event = self._clock()

    # -- output ------------------------------------------------------------

    def tick(self) -> Optional[str]:
        """One look at the clock: record the burst when it has been quiet long
        enough, or scan the whole vault when the timer is due. Returns the short
        hash of a commit made, or None. Never raises."""
        try:
            now = self._clock()
            with self._lock:
                due = bool(self._paths or self._everything) and now - self._last_event >= self.quiet
                paths, everything = (set(self._paths), self._everything) if due else (set(), False)
                if due:
                    self._paths.clear()
                    self._everything = False
            if due:
                return self._record(None if everything else sorted(paths))
            if now - self._last_scan >= self.scan_every:
                self._last_scan = now
                return self._record(None)
        except Exception as e:
            log.warning("vault watcher: %s", e)
        return None

    def _record(self, paths) -> Optional[str]:
        if not vault_history.enabled():
            return None
        with vault_history.write_lock(self.vault_root):
            commit = vault_history.snapshot_outside(self.vault_root, paths)
        if commit:
            self._on_recorded(commit)
        return commit

    def _invalidate_graph(self, _commit: str) -> None:
        nx_graph.invalidate()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._start_observer()
        self._thread = threading.Thread(target=self._run, name="loci-vault-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        observer, self._observer = self._observer, None
        if observer is not None:
            try:
                observer.stop()
                observer.join(timeout=2)
            except Exception as e:
                log.warning("vault watcher: stopping the observer failed: %s", e)
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(_POLL_SECONDS):
            self.tick()

    def _start_observer(self) -> None:
        """Native events when `watchdog` can provide them. Without them the timer
        scan alone still records edits, only later."""
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            log.warning("vault watcher: watchdog is not installed; scanning every %ss instead", self.scan_every)
            return

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                kind = getattr(event, "event_type", "")
                if kind == "opened" or kind == "closed_no_write":
                    return      # reads are not edits
                paths = [getattr(event, "src_path", ""), getattr(event, "dest_path", "")]
                if event.is_directory:
                    # A folder moved or removed carries files that may not each
                    # report; compare the whole vault. A folder history never
                    # records (the store, an editor's folder) is no reason to.
                    if kind in ("moved", "deleted", "created") and watcher._records(*[str(p) for p in paths if p]):
                        watcher.note(everything=True)
                    return
                watcher.note(*[str(p) for p in paths if p])

        try:
            observer = Observer()
            observer.schedule(Handler(), str(self.vault_root), recursive=True)
            observer.start()
            self._observer = observer
        except Exception as e:
            log.warning("vault watcher: native events unavailable (%s); scanning every %ss instead", e, self.scan_every)
