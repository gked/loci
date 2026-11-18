"""
The watcher records edits made outside Loci soon after they happen: bursts of
file events become one commit, a timer scan catches what events miss, and
nothing it does disturbs a Loci write.
"""

import sys
import threading
import time

import pytest

from loci import api
from loci.tools import nx_graph, vault_history
from loci.tools.vault_watcher import VaultWatcher


@pytest.fixture(autouse=True)
def history_on(monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")
    vault_history.set_source("api")
    vault_history._stat_cache.clear()
    vault_history._last_error.clear()
    vault_history._last_walk.clear()
    yield
    vault_history.set_source("api")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def started(tmp_vault):
    """A vault whose history exists, and a watcher on it with a clock the test moves."""
    api.save(type="document", title="First", body="hello",
             extra_fields={"status": "draft", "subtype": "note"})
    clock = Clock()
    seen = []
    watcher = VaultWatcher(tmp_vault, quiet=2.0, scan_every=45.0, clock=clock, on_recorded=seen.append)
    watcher.clock, watcher.seen = clock, seen
    return watcher


def _subjects(vault):
    from dulwich.repo import Repo
    repo = Repo(str(vault_history.history_dir(vault)))
    tip = repo.refs[vault_history.own_ref()]
    return [e.commit.message.decode().splitlines()[0] for e in repo.get_walker(include=[tip])]


def test_a_burst_is_one_commit_after_the_quiet_time(tmp_vault, started):
    (tmp_vault / "a.md").write_text("one")
    (tmp_vault / "b.md").write_text("two")
    started.note(str(tmp_vault / "a.md"))
    started.clock.advance(1.0)
    started.note(str(tmp_vault / "b.md"))        # a second event restarts the quiet time

    started.clock.advance(1.5)
    assert started.tick() is None                # 1.5 s since the last event: still a burst
    started.clock.advance(1.0)
    commit = started.tick()

    assert commit
    assert _subjects(tmp_vault)[0] == vault_history.OUTSIDE_MESSAGE
    assert started.seen == [commit]
    assert started.tick() is None                # the burst is spent


def test_a_deleted_file_is_recorded(tmp_vault, started):
    victim = next(tmp_vault.glob("*.md"))
    victim.unlink()
    started.note(str(victim))
    started.clock.advance(3)
    assert started.tick()
    assert vault_history.history(tmp_vault, victim)[0]["subject"] == vault_history.OUTSIDE_MESSAGE


def test_files_history_never_records_do_not_open_a_burst(tmp_vault, started):
    started.note(str(tmp_vault / ".loci" / "history" / "refs" / "heads" / "c-1"))
    started.note(str(tmp_vault / ".obsidian" / "workspace.json"))
    started.note(str(tmp_vault / "note.md.swp"))
    started.note(str(tmp_vault / ".DS_Store"))
    started.clock.advance(3)
    assert started.tick() is None
    assert started._paths == set() and not started._everything


def test_a_loci_write_adds_no_commit_from_the_watcher(tmp_vault, started):
    saved = api.save(type="document", title="Second", body="x",
                     extra_fields={"status": "draft", "subtype": "note"})
    before = _subjects(tmp_vault)
    started.note(saved["path"])                  # the event for Loci's own write
    started.clock.advance(3)

    assert started.tick() is None
    assert _subjects(tmp_vault) == before
    assert started.seen == []                    # and the graph is left alone


def test_the_timer_scan_catches_an_edit_no_event_reported(tmp_vault, started):
    (tmp_vault / "quiet.md").write_text("typed in an editor on a folder that gives no events")
    started.clock.advance(44)
    assert started.tick() is None
    started.clock.advance(2)
    assert started.tick()
    assert vault_history.history(tmp_vault, "quiet.md")


def test_a_folder_event_compares_the_whole_vault(tmp_vault, started):
    (tmp_vault / "moved.md").write_text("arrived inside a folder that was moved in")
    started.note(everything=True)
    started.clock.advance(3)
    assert started.tick()
    assert vault_history.history(tmp_vault, "moved.md")


def test_nothing_happens_while_history_is_off(tmp_vault, started, monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "0")
    (tmp_vault / "a.md").write_text("one")
    started.note(str(tmp_vault / "a.md"))
    started.clock.advance(3)
    assert started.tick() is None


def test_a_vault_without_history_is_left_alone(tmp_vault):
    clock = Clock()
    watcher = VaultWatcher(tmp_vault, clock=clock, on_recorded=lambda c: None)
    (tmp_vault / "a.md").write_text("one")
    watcher.note(str(tmp_vault / "a.md"))
    clock.advance(3)
    assert watcher.tick() is None
    assert not vault_history.is_repo(tmp_vault)   # the first Loci write makes the baseline


def test_an_error_in_recording_does_not_escape(tmp_vault, started, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk gone")
    monkeypatch.setattr(vault_history, "snapshot_outside", boom)
    started.note(str(tmp_vault / "a.md"))
    started.clock.advance(3)
    assert started.tick() is None                # no exception


def test_a_failed_recording_keeps_the_burst_for_the_next_try(tmp_vault, started, monkeypatch):
    real = vault_history.snapshot_outside
    calls = []

    def flaky(root, paths=None):
        calls.append(paths)
        if len(calls) == 1:
            raise RuntimeError("write lock timed out")
        return real(root, paths)

    monkeypatch.setattr(vault_history, "snapshot_outside", flaky)
    (tmp_vault / "a.md").write_text("one")
    started.note(str(tmp_vault / "a.md"))
    started.clock.advance(3)
    assert started.tick() is None                # the first try fails
    started.clock.advance(3)
    assert started.tick()                        # the second try, long before the 45 s scan
    assert calls[1] == calls[0]


def test_a_recorded_burst_makes_the_graph_rebuild(tmp_vault):
    api.save(type="document", title="First", body="hello",
             extra_fields={"status": "draft", "subtype": "note"})
    nx_graph.get(tmp_vault)
    built = nx_graph._built_at
    assert built > 0
    clock = Clock()
    watcher = VaultWatcher(tmp_vault, clock=clock)   # the default hook
    (tmp_vault / "a.md").write_text("one")
    watcher.note(str(tmp_vault / "a.md"))
    clock.advance(3)

    assert watcher.tick()
    assert nx_graph._built_at == 0.0


def test_files_from_another_computer_are_joined_not_recorded_as_outside(tmp_vault, tmp_path, monkeypatch):
    def as_computer(name):
        monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / f"cfg-{name}" / "config.yml"))
        return vault_history.computer_id()

    as_computer("a")
    api.save(type="document", title="Alpha", body="x", extra_fields={"status": "draft", "subtype": "note"})
    b = as_computer("b")
    beta = api.save(type="document", title="Beta", body="y", extra_fields={"status": "draft", "subtype": "note"})
    as_computer("a")                                  # Beta's file is on disk, A's branch lacks it
    clock = Clock()
    watcher = VaultWatcher(tmp_vault, clock=clock, on_recorded=lambda c: None)
    watcher.note(beta["path"])
    clock.advance(3)

    assert watcher.tick()
    subs = _subjects(tmp_vault)
    assert f"Synced from {b}" in subs
    assert vault_history.OUTSIDE_MESSAGE not in subs


@pytest.mark.parametrize("per_directory", [False, True], ids=["one-recursive-watch", "folder-by-folder"])
def test_a_real_file_event_ends_in_a_commit(tmp_vault, per_directory):
    """The native backend of this operating system (FSEvents, inotify or
    ReadDirectoryChangesW) reports a write, and the burst is recorded."""
    pytest.importorskip("watchdog")
    api.save(type="document", title="First", body="hello",
             extra_fields={"status": "draft", "subtype": "note"})
    done = threading.Event()
    watcher = VaultWatcher(tmp_vault, quiet=0.3, scan_every=3600, on_recorded=lambda c: done.set(),
                           per_directory=per_directory)
    watcher.start()
    try:
        if watcher._observer is None:
            pytest.skip("no native file events here; the timer scan covers this platform")
        time.sleep(0.5)                           # let the observer attach
        (tmp_vault / "typed-by-hand.md").write_text("hello from an editor")
        assert done.wait(10), "no commit within 10 s of a file event"
        assert vault_history.history(tmp_vault, "typed-by-hand.md")
        assert watcher.mode == "events"
    finally:
        watcher.stop()
    assert watcher._thread is None and watcher._observer is None


# ---------------------------------------------------------------------------
# What to watch, and what happens when the operating system says no more
# ---------------------------------------------------------------------------

import errno
import logging


class FakeObserver:
    """Records what is watched, and refuses after `limit` watches, as inotify does.
    `fail_at_start` makes start() refuse instead: a watchdog observer that schedules
    folders before start() reports the limit there."""
    def __init__(self, limit=None, fail_at_start=False):
        self.limit, self.fail_at_start = limit, fail_at_start
        self.scheduled, self.unscheduled, self.started, self.stopped = [], [], False, False

    def schedule(self, handler, path, recursive=False):
        if self.limit is not None and len(self.scheduled) - len(self.unscheduled) >= self.limit:
            raise OSError(errno.ENOSPC, "inotify watch limit reached")
        self.scheduled.append((path, recursive))
        return path

    def unschedule(self, watch):
        self.unscheduled.append(watch)

    def start(self):
        if self.fail_at_start:
            raise OSError(errno.ENOSPC, "inotify watch limit reached")
        self.started = True

    def stop(self):
        self.stopped = True

    def join(self, timeout=None):
        pass


def _watcher(vault, observer, per_directory=True):
    return VaultWatcher(vault, observer_factory=lambda: observer, per_directory=per_directory)


def test_on_linux_the_store_and_editor_folders_are_not_watched(tmp_vault):
    for d in (".loci/history/objects/ab", ".obsidian", ".git", "meta", "sub/deeper"):
        (tmp_vault / d).mkdir(parents=True, exist_ok=True)
    observer = FakeObserver()
    w = _watcher(tmp_vault, observer)
    w._start_observer()
    watched = {p for p, _ in observer.scheduled}
    assert str(tmp_vault) in watched
    assert str(tmp_vault / "meta") in watched and str(tmp_vault / "sub" / "deeper") in watched
    assert not [p for p in watched if "/.loci" in p or "/.obsidian" in p or "/.git" in p]
    assert all(recursive is False for _, recursive in observer.scheduled)
    assert observer.started and w.mode == "events"


def test_on_macos_and_windows_one_recursive_watch_is_made(tmp_vault):
    (tmp_vault / "meta").mkdir(exist_ok=True)
    observer = FakeObserver()
    w = _watcher(tmp_vault, observer, per_directory=False)
    w._start_observer()
    assert observer.scheduled == [(str(tmp_vault), True)]
    assert w.mode == "events"


def test_a_new_folder_is_watched_when_it_appears(tmp_vault):
    from watchdog.events import DirCreatedEvent
    observer = FakeObserver()
    w = _watcher(tmp_vault, observer)
    w._start_observer()
    (tmp_vault / "fresh" / "inner").mkdir(parents=True)
    w._handler.on_any_event(DirCreatedEvent(str(tmp_vault / "fresh")))
    watched = {p for p, _ in observer.scheduled}
    assert str(tmp_vault / "fresh") in watched and str(tmp_vault / "fresh" / "inner") in watched
    (tmp_vault / ".loci" / "newdir").mkdir(parents=True, exist_ok=True)
    w._handler.on_any_event(DirCreatedEvent(str(tmp_vault / ".loci" / "newdir")))
    assert str(tmp_vault / ".loci" / "newdir") not in {p for p, _ in observer.scheduled}


def test_reaching_the_watch_limit_keeps_what_is_watched_and_says_how_to_raise_it(tmp_vault, caplog):
    for d in ("a", "b", "c"):
        (tmp_vault / d).mkdir(exist_ok=True)
    observer = FakeObserver(limit=2)
    w = _watcher(tmp_vault, observer)
    with caplog.at_level(logging.WARNING):
        w._start_observer()
    assert len(observer.scheduled) == 2 and observer.started
    assert w.mode == "partial"
    assert "max_user_watches" in caplog.text


def test_no_watch_at_all_leaves_the_timer_scan(tmp_vault, caplog):
    observer = FakeObserver(limit=0)
    w = _watcher(tmp_vault, observer)
    with caplog.at_level(logging.WARNING):
        w._start_observer()
    assert w.mode == "scan" and w._observer is None
    assert "max_user_watches" in caplog.text


def test_the_timer_scan_still_records_an_edit_in_a_folder_the_limit_left_out(tmp_vault):
    api.save(type="document", title="First", body="hello", extra_fields={"status": "draft", "subtype": "note"})
    clock = Clock()
    w = VaultWatcher(tmp_vault, scan_every=45.0, clock=clock, on_recorded=lambda c: None,
                     observer_factory=lambda: FakeObserver(limit=0), per_directory=True)
    w._start_observer()
    (tmp_vault / "unwatched.md").write_text("---\nuid: 1234abcd\n---\n")
    clock.advance(46)
    assert w.tick()
    assert "Changes made outside Loci" in _subjects(tmp_vault)[0]


def test_stop_survives_an_observer_that_never_started(tmp_vault):
    w = _watcher(tmp_vault, FakeObserver(limit=0))
    w._start_observer()
    w.stop()


def test_a_limit_reported_by_start_says_how_to_raise_it_and_stops_the_observer(tmp_vault, caplog):
    observer = FakeObserver(fail_at_start=True)
    w = _watcher(tmp_vault, observer)
    with caplog.at_level(logging.WARNING):
        w._start_observer()
    assert w.mode == "scan" and w._observer is None and observer.stopped
    assert "max_user_watches" in caplog.text


def test_the_limit_is_warned_about_once(tmp_vault, caplog):
    from watchdog.events import DirCreatedEvent
    (tmp_vault / "a").mkdir(exist_ok=True)
    observer = FakeObserver(limit=1)
    w = _watcher(tmp_vault, observer)
    with caplog.at_level(logging.WARNING):
        w._start_observer()
        for name in ("n1", "n2", "n3"):
            (tmp_vault / name).mkdir()
            w._handler.on_any_event(DirCreatedEvent(str(tmp_vault / name)))
    assert caplog.text.count("max_user_watches") == 1
    assert len(observer.scheduled) == 1 and w.mode == "partial"


def test_a_folder_deleted_and_made_again_is_watched_again(tmp_vault):
    from watchdog.events import DirCreatedEvent, DirDeletedEvent
    observer = FakeObserver()
    w = _watcher(tmp_vault, observer)
    w._start_observer()
    folder = tmp_vault / "cycle"
    folder.mkdir()
    w._handler.on_any_event(DirCreatedEvent(str(folder)))
    assert str(folder) in w._watched
    folder.rmdir()
    w._handler.on_any_event(DirDeletedEvent(str(folder)))
    assert str(folder) not in w._watched and str(folder) in observer.unscheduled
    folder.mkdir()
    w._handler.on_any_event(DirCreatedEvent(str(folder)))
    assert str(folder) in w._watched
    assert [p for p, _ in observer.scheduled].count(str(folder)) == 2


def test_a_freed_watch_lets_the_watcher_try_again_after_the_limit(tmp_vault):
    from watchdog.events import DirCreatedEvent, DirDeletedEvent
    (tmp_vault / "a").mkdir(exist_ok=True)
    observer = FakeObserver(limit=2)
    w = _watcher(tmp_vault, observer)
    w._start_observer()                              # the vault folder and "a"
    (tmp_vault / "b").mkdir()
    w._handler.on_any_event(DirCreatedEvent(str(tmp_vault / "b")))
    assert str(tmp_vault / "b") not in w._watched and w._limit_hit
    (tmp_vault / "a").rmdir()
    w._handler.on_any_event(DirDeletedEvent(str(tmp_vault / "a")))
    w._handler.on_any_event(DirCreatedEvent(str(tmp_vault / "b")))
    assert str(tmp_vault / "b") in w._watched


def test_a_folder_named_like_a_swap_file_is_still_watched(tmp_vault):
    (tmp_vault / "notes~").mkdir()
    observer = FakeObserver()
    w = _watcher(tmp_vault, observer)
    w._start_observer()
    assert str(tmp_vault / "notes~") in w._watched


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="folder-by-folder watching is the Linux mode; "
                    "FSEvents does not report folders to a non-recursive watch")
def test_a_folder_made_while_running_is_seen_by_a_real_observer(tmp_vault):
    pytest.importorskip("watchdog")
    api.save(type="document", title="First", body="hello", extra_fields={"status": "draft", "subtype": "note"})
    done = threading.Event()
    w = VaultWatcher(tmp_vault, quiet=0.3, scan_every=3600, on_recorded=lambda c: done.set(), per_directory=True)
    w.start()
    try:
        if w._observer is None:
            pytest.skip("no native file events here; the timer scan covers this platform")
        time.sleep(0.5)
        (tmp_vault / "later" / "inner").mkdir(parents=True)
        deadline = time.time() + 10
        while str(tmp_vault / "later" / "inner") not in w._watched and time.time() < deadline:
            time.sleep(0.1)
        assert str(tmp_vault / "later" / "inner") in w._watched
    finally:
        w.stop()
