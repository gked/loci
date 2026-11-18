"""
vault_history.py

Change history for the vault, kept in a Git-format repository that Loci owns.

The repository lives at vault_root/.loci/history, apart from any `.git` the
user keeps in the vault, and is read and written with dulwich, a pure-Python
Git library. Nothing here runs the `git` command, so the history works on a
machine that has no Git installed. The repository has no index and no working
tree of its own: a commit is built straight from the files on disk, so
`git --git-dir vault/.loci/history log --all` and `show` read it, and a second
process can write beside the first without an index lock.

The vault can sync across computers (Nextcloud, say), and a sync tool cannot
merge two writers of one file. So each computer writes only its own branch,
refs/heads/<computer id>; the id is made once and kept beside the config, never
in the vault. Commit objects are named by their hash and never change, so they
sync safely. The history reads every branch together. When files arrive from
another computer, they are recorded as a merge commit that has that computer's
branch as its second parent, not as an edit made outside Loci. HEAD never moves:
it names refs/heads/main, the line every store had before this, so the one
file every computer shares is the same on all of them.

Every API write calls record() once, after the file is on disk. record() makes
one commit that holds exactly the paths that write touched. Before that it
commits whatever else differs from the last commit — edits made by hand, by
Obsidian or by a sync tool while Loci was not looking — as one "Changes made
outside Loci" commit, so those edits are never folded into an unrelated
change. Assets live beside the vault, not inside it, so they are never in the
repository.

History is a convenience, never a gate: a locked ref or a read-only disk is
logged and swallowed, and the write that triggered it still succeeds.
status() says whether it is working. Set LOCI_VAULT_HISTORY=0 to turn it off.

Who made a change is the commit author. The default is the Loci service
identity; a caller that knows the real user (a future editor endpoint) passes
`author="Name <email>"`. The channel that made the call (mcp, ui) goes in a
`Source:` trailer, so the two stay separate.
"""

import difflib
import fnmatch
import json
import logging
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from dulwich.diff_tree import tree_changes
from dulwich.errors import MissingCommitError
from dulwich.file import FileLocked
from dulwich.graph import can_fast_forward, find_merge_base
from dulwich.index import commit_tree
from dulwich.object_store import iter_tree_contents, tree_lookup_path
from dulwich.objects import ZERO_SHA, Blob, Commit
from dulwich.repo import Repo
from filelock import FileLock, Timeout

from loci.tools.frontmatter import split_frontmatter

log = logging.getLogger(__name__)

SERVICE_AUTHOR = "loci <loci@localhost>"
HISTORY_DIR = Path(".loci") / "history"
LEGACY_BRANCH = b"refs/heads/main"   # HEAD names it on every computer; no write moves it
COMPUTER_ID_FILE = "computer-id"
_ID_RE = re.compile(r"c-[0-9a-f]{8}")
BASELINE_MESSAGE = "Baseline: vault before history tracking"
OUTSIDE_MESSAGE = "Changes made outside Loci"
RENAMED_PREFIX = "Renamed: "      # subject of a commit that holds a rename made outside Loci
SYNCED_MESSAGE = "Synced from"     # + the other computer's id

# The MCP and UI servers are separate processes that can commit to the same
# repository, on the same computer, so on the same branch. The branch is moved
# with a compare-and-swap, so the loser of a race rebuilds its commit on the
# winner's and tries again.
_RACE_ATTEMPTS = 3
_RACE_WAIT_SECONDS = 0.2

# What history never records: the store itself, a Git repository the user keeps
# in the vault, Obsidian's settings folder (workspace.json changes on every
# click), and the editor and OS litter that Loci writes around.
_SKIP_DIRS = {".git", ".loci", ".obsidian"}
_SKIP_FILES = (".DS_Store", "*.tmp", "*.swp", "*~", ".#*")
_FILE_MODE = 0o100644

# Finding what changed outside Loci walks every file, so its cost grows with the
# vault. While a walk stays under _SCAN_FAST_SECONDS it runs on every write, so
# an outside edit gets its own commit just before the write that follows it.
# Past that, the walk runs at most once per _SLOW_SCAN_INTERVAL_SECONDS and an
# outside edit is recorded by the next walk. The write's own files are always
# read from disk, so no text is lost either way.
_SCAN_FAST_SECONDS = 0.1
_SLOW_SCAN_INTERVAL_SECONDS = 60.0
_clock = time.monotonic

# vault root -> (when the last full walk ended, how long it took).
_last_walk: dict[str, tuple[float, float]] = {}

# The channel this process serves; see set_source().
_source = "api"

# (vault root, key) -> ((mtime_ns, size, ctime_ns), blob id): lets a write skip re-reading
# the files that have not changed since the last one.
_stat_cache: dict[tuple[str, bytes], tuple[tuple[int, int, int], bytes]] = {}

# vault root -> why the last attempt failed. Cleared by the next success. The MCP
# and UI servers are separate processes, so the reason is also written to
# status_path(), where the other one reads it; this dict is the fallback for a
# disk that will not take that file either.
_last_error: dict[str, str] = {}
# Bumped by every _set_error in this process, so two stamps of the same reason
# still differ when the status file has no usable mtime.
_error_count = 0
# One file per computer: a failure on one computer must not show on another.
STATUS_DIR = Path(".loci")


# A commit as the agent names it: a hash, optionally stepped back ("abc123~1" is
# the version before abc123 — how a deleted file is reached), or HEAD.
_REV_RE = re.compile(r"(?:[0-9a-f]{4,40}|HEAD)(?:~\d{1,4})?")


class HistoryError(Exception):
    """A history request that cannot be answered: no store, bad commit, no such
    version. The message is for the agent to read."""


_computer_ids: dict[str, str] = {}     # id file path -> id, so a write does not re-read it


def computer_id() -> str:
    """This computer's id, made on first use and kept in the config folder next
    to config.yml. It is never in the vault, because a vault that syncs would
    hand one computer's id to all the others. The hostname is no substitute: it
    changes, and two computers can share one. When the file cannot be written
    the id lasts for this process only, which costs a branch per run."""
    from loci.tools.vault_init import config_path
    path = config_path().parent / COMPUTER_ID_FILE
    key = str(path)
    known = _computer_ids.get(key)
    if known:
        return known

    def read() -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    found = read()
    if not _ID_RE.fullmatch(found):
        found = "c-" + uuid.uuid4().hex[:8]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(path, "x", encoding="utf-8") as handle:   # two processes starting at once agree
                    handle.write(found + "\n")
            except FileExistsError:
                other = read()
                if _ID_RE.fullmatch(other):
                    found = other
                else:                                               # a damaged file: replace it
                    path.write_text(found + "\n", encoding="utf-8")
        except OSError as e:
            log.warning("computer id cannot be saved (%s); using %s for this run only", e, found)
    _computer_ids[key] = found
    return found


def own_ref() -> bytes:
    """The branch this computer writes."""
    return b"refs/heads/" + computer_id().encode("ascii")


def status_path(vault_root: Path) -> Path:
    return Path(vault_root) / STATUS_DIR / f"history-status.{computer_id()}.json"


def _short(commit_id: bytes) -> str:
    return commit_id.decode("ascii")[:7]


def _set_error(vault_root: Path, reason: str) -> None:
    """Show `reason` to every process through status_path(). Only when that file
    cannot be written does this process keep the reason to itself: a copy kept
    beside a working file would outlive the other process clearing it."""
    global _error_count
    _error_count += 1
    root = str(Path(vault_root).resolve())
    try:
        path = status_path(vault_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"error": reason}), encoding="utf-8")
        _last_error.pop(root, None)
    except OSError:
        _last_error[root] = reason


def _clear_error(vault_root: Path) -> None:
    _last_error.pop(str(Path(vault_root).resolve()), None)
    try:
        status_path(vault_root).unlink()
    except OSError:
        pass


def _read_error(vault_root: Path) -> Optional[str]:
    try:
        reason = json.loads(status_path(vault_root).read_text(encoding="utf-8")).get("error")
        if reason:
            return reason
    except (OSError, ValueError, AttributeError):
        pass
    return _last_error.get(str(Path(vault_root).resolve()))


def error_stamp(vault_root: Path) -> Optional[tuple[str, Optional[int], int]]:
    """The current error flag and when it was written, None when there is none.
    Two stamps differ when a failure happened between them, even for the same
    reason: that is how a caller tells its own failure from an older one."""
    reason = _read_error(vault_root)
    if not reason:
        return None
    try:
        return reason, status_path(vault_root).stat().st_mtime_ns, _error_count
    except OSError:
        return reason, None, _error_count


def _walk_due(root: str) -> bool:
    last = _last_walk.get(root)
    if last is None:
        return True
    ended, took = last
    return took < _SCAN_FAST_SECONDS or _clock() - ended >= _SLOW_SCAN_INTERVAL_SECONDS


def set_source(name: str) -> None:
    """Name the channel this process serves ('mcp', 'ui'). Each entry point
    calls it once; every commit it makes then carries it in the trailer."""
    global _source
    _source = name


def enabled() -> bool:
    return os.environ.get("LOCI_VAULT_HISTORY", "1").strip().lower() not in {"0", "false", "no", "off"}


def history_dir(vault_root: Path) -> Path:
    return Path(vault_root) / HISTORY_DIR


def is_repo(vault_root: Path) -> bool:
    return (history_dir(vault_root) / "HEAD").is_file()


def status(vault_root: Path) -> dict:
    """{state, detail} for display. `state` is 'on' (a repository exists and
    the last write to it worked), 'ready' (enabled; the first write creates it),
    'off' (turned off) or 'error' (the last write could not be recorded)."""
    if not enabled():
        return {"state": "off", "detail": "Turned off by LOCI_VAULT_HISTORY."}
    reason = _read_error(vault_root)
    if reason:
        return {"state": "error", "detail": reason}
    if is_repo(vault_root):
        return {"state": "on", "detail": ""}
    return {"state": "ready", "detail": "The first write starts it."}


def _split_author(author: str) -> tuple[str, str]:
    """'Name <email>' -> (name, email). A bare name gets a local address."""
    if "<" in author and author.rstrip().endswith(">"):
        name, _, rest = author.partition("<")
        return name.strip() or "loci", rest.rstrip(" >") or "loci@localhost"
    return author.strip() or "loci", "loci@localhost"


def _open(vault_root: Path, create: bool = False) -> Optional[Repo]:
    path = history_dir(vault_root)
    if is_repo(vault_root):
        repo = Repo(str(path))
        # A process that stopped between init_bare and set_symbolic_ref leaves
        # HEAD on "master". HEAD is one file every computer shares, so it must
        # be the same everywhere: it names the legacy line and no write moves it.
        names, _ = repo.refs.follow(b"HEAD")
        if names[-1] != LEGACY_BRANCH:
            repo.refs.set_symbolic_ref(b"HEAD", LEGACY_BRANCH)
        return repo
    if not create:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        repo = Repo.init_bare(str(path), mkdir=True)
    except FileExistsError:
        # The other process (MCP and UI both write) created the store first.
        return Repo(str(path))
    repo.refs.set_symbolic_ref(b"HEAD", LEGACY_BRANCH)
    return repo


def _eligible(rel: Path) -> bool:
    return not any(part in _SKIP_DIRS for part in rel.parts) and not any(
        fnmatch.fnmatch(rel.name, pattern) for pattern in _SKIP_FILES
    )


def folder_recorded(rel: Path) -> bool:
    """True when history records files in this vault-relative folder: not the store,
    an editor's folder or a user's `.git`. Folder names are not matched against the
    file-name patterns (swap files and the like), which apply to files only."""
    return not any(part in _SKIP_DIRS for part in rel.parts)


def _key(rel: Path) -> bytes:
    return rel.as_posix().encode("utf-8", "surrogateescape")


def _relative(vault_root: Path, paths: Iterable[Path | str]) -> list[bytes]:
    """Repository keys for paths inside the vault. A path outside it, inside
    the store or a user's `.git`, or one history never records, is dropped."""
    root = vault_root.resolve()
    out = []
    for p in paths:
        p = Path(p)
        p = p if p.is_absolute() else root / p
        try:
            rel = p.resolve().relative_to(root)
        except ValueError:
            continue
        if rel.parts and _eligible(rel):
            out.append(_key(rel))
    return out


def _scan(vault_root: Path) -> dict[bytes, tuple[int, int, int]]:
    """Every file history records, as key -> (mtime_ns, size, ctime_ns). The change
    time is in the key because a tool can restore a file's modification time
    (`rsync -t`) but not its change time."""
    found: dict[bytes, tuple[int, int, int]] = {}
    stack = [vault_root]
    while stack:
        try:
            scan = os.scandir(stack.pop())
        except OSError:
            continue  # a directory removed mid-walk by Obsidian or a sync tool
        with scan as entries:
            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir():
                        if entry.name not in _SKIP_DIRS:
                            stack.append(Path(entry.path))
                        continue
                    rel = Path(entry.path).relative_to(vault_root)
                    if entry.is_file() and _eligible(rel):
                        st = entry.stat()
                        found[_key(rel)] = (st.st_mtime_ns, st.st_size, st.st_ctime_ns)
                except OSError:
                    continue  # the file went away between listing and stat
    return found


def _usable(repo: Repo, sha: bytes) -> bool:
    """True when `sha` is a commit whose tree is in the store. A sync tool copies
    files in any order, so a branch can arrive before the objects it names."""
    try:
        commit = repo.object_store[sha]
        return isinstance(commit, Commit) and commit.tree in repo.object_store
    except KeyError:
        return False


def _tips(repo: Repo) -> dict[bytes, bytes]:
    """Every branch of every computer, and the legacy `main`: id -> commit id. A
    branch whose objects have not all arrived is left out until they do."""
    return {name: sha for name, sha in repo.refs.as_dict(b"refs/heads").items() if _usable(repo, sha)}


def _head(repo: Repo) -> tuple[Optional[bytes], dict[bytes, tuple[int, bytes]]]:
    """(commit id, {key: (mode, blob id)}) for this computer's branch, or
    (None, {}) before the first commit. A computer with no branch of its own yet
    starts from the newest commit of any other: its first write then continues
    that line, which is how a vault from before per-computer branches is taken
    over, and how a new computer joins."""
    tips = _tips(repo)
    head = tips.get(computer_id().encode("ascii"))
    if head is None and tips:
        head = max(tips.values(), key=lambda sha: (repo.object_store[sha].commit_time, sha))
    if head is None:
        return None, {}
    tree = repo.object_store[head].tree
    return head, {e.path: (e.mode, e.sha) for e in iter_tree_contents(repo.object_store, tree)}


def _differences(
    vault_root: Path,
    entries: dict[bytes, tuple[int, bytes]],
    *,
    skip: frozenset[bytes] = frozenset(),
    only: Optional[Iterable[bytes]] = None,
    walked: Optional[dict[bytes, tuple[int, int, int]]] = None,
) -> dict[bytes, Optional[Blob]]:
    """What differs between the vault and the last commit: key -> Blob for a
    file that is new or changed, key -> None for one that is gone. `only` limits
    the comparison to those keys and always reads them from disk (the write that
    just happened); otherwise it covers the whole vault and trusts the stat
    cache for files that have not moved. `skip` leaves keys out. `walked` is a
    _scan() the caller already made, so a retry does not walk the vault again."""
    root = str(vault_root.resolve())
    if only is None:
        on_disk = walked if walked is not None else _scan(vault_root)
        candidates = set(on_disk) | set(entries)
        for gone in [k for (r, k) in _stat_cache if r == root and k not in on_disk]:
            del _stat_cache[(root, gone)]
    else:
        candidates = set(only)
        on_disk = {}
        for key in candidates:
            path = vault_root / os.fsdecode(key)
            if path.is_file() and not path.is_symlink():
                st = path.stat()
                on_disk[key] = (st.st_mtime_ns, st.st_size, st.st_ctime_ns)

    changes: dict[bytes, Optional[Blob]] = {}
    for key in candidates - skip:
        sig = on_disk.get(key)
        if sig is None:
            if key in entries:
                changes[key] = None
            continue
        cached = _stat_cache.get((root, key))
        if only is None and cached and cached[0] == sig and key in entries and entries[key][1] == cached[1]:
            continue
        try:
            blob = Blob.from_string((vault_root / os.fsdecode(key)).read_bytes())
        except FileNotFoundError:
            if key in entries:
                changes[key] = None
            continue
        _stat_cache[(root, key)] = (sig, blob.id)
        if key in entries and entries[key][1] == blob.id:
            continue
        changes[key] = blob
    return changes


def _commit(
    repo: Repo,
    parent: Optional[bytes],
    entries: dict[bytes, tuple[int, bytes]],
    changes: dict[bytes, Optional[Blob]],
    message: str,
    author: str,
    *,
    force: bool = False,
    also: tuple[bytes, ...] = (),
) -> Optional[tuple[Commit, dict[bytes, tuple[int, bytes]]]]:
    """Commit `entries` with `changes` applied. None when that is the tree the
    parent already has (nothing to commit), unless `force` asks for it anyway.
    `also` names more parents: the other computers' commits a merge joins."""
    new = dict(entries)
    for key, blob in changes.items():
        if blob is None:
            new.pop(key, None)
        else:
            repo.object_store.add_object(blob)
            new[key] = (_FILE_MODE, blob.id)
    tree_id = commit_tree(repo.object_store, [(k, sha, mode) for k, (mode, sha) in sorted(new.items())])
    if parent is not None and not force and repo.object_store[parent].tree == tree_id:
        return None
    name, email = _split_author(author)
    now = int(time.time())
    offset = time.localtime(now).tm_gmtoff or 0
    commit = Commit()
    commit.tree = tree_id
    commit.parents = ([parent] if parent is not None else []) + list(also)
    commit.author = commit.committer = f"{name} <{email}>".encode("utf-8")
    commit.author_time = commit.commit_time = now
    commit.author_timezone = commit.commit_timezone = offset
    commit.encoding = b"UTF-8"
    commit.message = message.encode("utf-8")
    repo.object_store.add_object(commit)
    return commit, new


def _advance(repo: Repo, old: Optional[bytes], new: bytes) -> bool:
    """Move this computer's branch from `old` to `new`. False when another
    process moved it first. Raises FileLocked when something holds the branch
    lock. A branch that does not exist yet is created, whatever `old` is: `old`
    is then another computer's commit that this one starts from."""
    ref = own_ref()
    try:
        current = repo.refs[ref]
    except KeyError:
        current = None
    if current is None:
        # dulwich skips the comparison for None; ZERO_SHA means "must not exist
        # yet", so two first commits cannot both win.
        return repo.refs.set_if_equals(ref, ZERO_SHA, new)
    if old is None:
        return False
    return repo.refs.set_if_equals(ref, old, new)


# (store, commit id) pairs this computer's branch is known to contain. A commit
# stays an ancestor once it is one, so a write never walks the graph for it twice.
_joined: set[tuple[str, bytes]] = set()


def _incoming(
    repo: Repo,
    vault_root: Path,
    head: bytes,
    entries: dict[bytes, tuple[int, bytes]],
    tip: bytes,
    skip: frozenset[bytes],
    settled: frozenset[bytes] = frozenset(),
) -> Optional[dict[bytes, Optional[Blob]]]:
    """What the vault still lacks of another computer's line, when the vault now
    holds every change that line made since it forked from this one: key -> Blob
    for a file to take, key -> None for one to drop. None when any of those
    changes has not reached the vault, or when it clashes with the write in
    progress. Joining a line before it has fully arrived would let a later
    three-way merge mistake the missing change for a revert. `settled` names
    files whose changes on that line a merge has just taken in by hand: the disk
    holds the merge result, not their blob, and that is not a missing change."""
    bases = find_merge_base(repo, [head, tip])
    base_tree = repo.object_store[bases[0]].tree if bases else None
    theirs: dict[bytes, Optional[bytes]] = {}
    for change in tree_changes(repo.object_store, base_tree, repo.object_store[tip].tree):
        theirs[change.new.path or change.old.path] = change.new.sha
    for key in settled:
        theirs.pop(key, None)
    if skip & theirs.keys():
        return None
    on_disk = _differences(vault_root, entries, only=theirs.keys())
    take: dict[bytes, Optional[Blob]] = {}
    for key, sha in theirs.items():
        if key in on_disk:
            blob = on_disk[key]
            have = blob.id if blob is not None else None
            take[key] = blob
        else:
            have = entries.get(key, (None, None))[1]
        if have != sha:
            return None
    return take


def _merge_incoming(
    repo: Repo,
    vault_root: Path,
    head: bytes,
    entries: dict[bytes, tuple[int, bytes]],
    advance,
    skip: frozenset[bytes] = frozenset(),
    settled: frozenset[bytes] = frozenset(),
) -> Optional[tuple[bytes, dict[bytes, tuple[int, bytes]]]]:
    """Record the files that arrived from other computers as a merge commit with
    that computer's branch as the second parent, not as an edit made outside
    Loci. Returns the new (head, entries), or None when another process moved the
    branch first and the caller must start again. `advance(old, new)` moves the
    branch and says whether it worked."""
    own = computer_id().encode("ascii")
    store = str(repo.path)
    pending = []
    for name, tip in _tips(repo).items():
        if name == own or tip == head or (store, tip) in _joined:
            continue
        if _descends(repo, tip, head):
            _joined.add((store, tip))
            continue
        pending.append((repo.object_store[tip].commit_time, name, tip))
    for _, name, tip in sorted(pending):
        try:
            take = _incoming(repo, vault_root, head, entries, tip, skip, settled)
        except KeyError:
            continue    # objects of that line are still arriving
        if take is None:
            continue
        made = _commit(repo, head, entries, take,
                       f"{SYNCED_MESSAGE} {name.decode('utf-8', 'replace')}\n\nSource: sync",
                       SERVICE_AUTHOR, force=True, also=(tip,))
        if not advance(head, made[0].id):
            return None
        head, entries = made[0].id, made[1]
        _joined.add((store, tip))
    return head, entries


def _renames(
    repo: Repo,
    entries: dict[bytes, tuple[int, bytes]],
    changes: dict[bytes, Optional[Blob]],
) -> list[tuple[bytes, bytes]]:
    """(old, new) for each note that moved: one file is gone and one is new, and
    both carry the same uid. A uid that is not alone on either side is not a
    rename (a copy, or two notes swapped), so it is left out."""
    gone: dict[str, list[bytes]] = {}
    added: dict[str, list[bytes]] = {}
    for key, blob in changes.items():
        if not key.endswith(b".md"):
            continue
        if blob is None:
            data = repo[entries[key][1]].data if key in entries else None
        elif key not in entries:
            data = blob.data
        else:
            continue
        uid = _uid_of(data) if data is not None else None
        if uid:
            (gone if blob is None else added).setdefault(uid, []).append(key)
    return sorted(
        (olds[0], added[uid][0])
        for uid, olds in gone.items()
        if len(olds) == 1 and len(added.get(uid, [])) == 1
    )


def _uid_of(data: bytes) -> Optional[str]:
    header, _ = split_frontmatter(data.decode("utf-8", "replace"))
    match = header and _UID_LINE.search(header.encode("utf-8"))
    return match.group(1).decode("utf-8", "replace") if match else None


def _name_in_message(name: bytes) -> str:
    """A file name made safe for a commit subject: bytes that are not UTF-8 become
    U+FFFD (a lone surrogate would make the commit message fail to encode), and a
    control character such as a newline becomes "?" (it would split the subject)."""
    return re.sub(r"[\x00-\x1f\x7f]", "?", name.decode("utf-8", "replace"))


def _outside_message(
    repo: Repo,
    entries: dict[bytes, tuple[int, bytes]],
    changes: dict[bytes, Optional[Blob]],
) -> str:
    """Message for a commit of edits made outside Loci. A note moved or renamed
    gives "Renamed: old.md → new.md" (up to three pairs); any other file in the
    same commit is counted on a second line. No rename gives OUTSIDE_MESSAGE."""
    pairs = _renames(repo, entries, changes)
    if not pairs:
        return OUTSIDE_MESSAGE
    shown = ", ".join(f"{_name_in_message(old)} → {_name_in_message(new)}" for old, new in pairs[:3])
    if len(pairs) > 3:
        shown += f" and {len(pairs) - 3} more"
    others = len(changes) - 2 * len(pairs)
    message = RENAMED_PREFIX + shown
    if others > 0:
        message += f"\n\nAlso changed outside Loci: {others} other file{'s' if others != 1 else ''}."
    return message


def record(
    vault_root: Path,
    message: str,
    paths: Iterable[Path | str],
    *,
    author: Optional[str] = None,
    source: Optional[str] = None,
    settled: Iterable[Path | str] = (),
) -> bool:
    """Commit `paths` (files written or deleted) with `message`, after one
    commit for anything else that changed outside Loci. `settled` names files in
    `paths` that merge another computer's edit of the same file: that computer's
    line is then joined even though the file is not its version. Returns the new commit's
    short hash, or None when no commit was made (history off, nothing changed,
    or a failure). Never raises."""
    if not enabled():
        return None
    vault_root = Path(vault_root)
    try:
        specs = _relative(vault_root, paths)
        settled_keys = frozenset(_relative(vault_root, settled))
        if not specs or not vault_root.is_dir():
            return None
        repo = _open(vault_root, create=True)
        # A title can hold a newline; the subject and the trailer must not.
        message = " ".join(message.split())
        full = f"{message}\n\nSource: {source or _source}"
        locked = False
        walked = None

        def advance(old, new) -> bool:
            nonlocal locked
            try:
                return _advance(repo, old, new)
            except FileLocked:
                locked = True
                return False

        for attempt in range(_RACE_ATTEMPTS):
            if attempt:
                if locked and attempt > 1:
                    break   # a lock that outlives one retry is not a race
                time.sleep(_RACE_WAIT_SECONDS)
            locked = False
            head, entries = _head(repo)
            if head is not None:
                joined = _merge_incoming(repo, vault_root, head, entries, advance, frozenset(specs), settled_keys)
                if joined is None:
                    continue
                head, entries = joined

            # Whatever else changed since the last commit. The write in
            # progress stays out of it so that write gets its own commit.
            root = str(vault_root.resolve())
            if head is None or _walk_due(root):
                if walked is None:
                    started = _clock()
                    walked = _scan(vault_root)
                    _last_walk[root] = (_clock(), _clock() - started)
                outside = _differences(vault_root, entries, skip=frozenset(specs), walked=walked)
            else:
                outside = {}
            if outside or head is None:
                made = _commit(repo, head, entries, outside,
                               BASELINE_MESSAGE if head is None else _outside_message(repo, entries, outside),
                               SERVICE_AUTHOR, force=head is None)
                if made is not None:
                    if not advance(head, made[0].id):
                        continue
                    head, entries = made[0].id, made[1]

            made = _commit(repo, head, entries, _differences(vault_root, entries, only=specs),
                           full, author or SERVICE_AUTHOR)
            if made is None:
                # "Nothing to commit" is normal: a patch that changed no bytes.
                _clear_error(vault_root)
                return None
            if advance(head, made[0].id):
                _clear_error(vault_root)
                return _short(made[0].id)
        if locked:
            lock = history_dir(vault_root) / (own_ref().decode("ascii") + ".lock")
            raise OSError(f"the history branch is locked by {lock}; "
                          "if no Loci process is running, delete that file")
        raise OSError("another process kept moving the history branch")
    except Exception as e:
        log.warning("vault history unavailable: %s", e)
        _set_error(vault_root, str(e))
        return None


def ensure_baseline(vault_root: Path) -> None:
    """Commit the vault as it is now when history has no commit yet. Call it
    before a write that edits an existing file: the first record() leaves the
    file it was given out of the baseline, so without this the text from before
    the edit is in no commit. Cheap once the store exists. Never raises."""
    if not enabled():
        return
    vault_root = Path(vault_root)
    try:
        if not vault_root.is_dir():
            return
        repo = _open(vault_root, create=True)
        head, entries = _head(repo)
        if head is not None:
            return
        made = _commit(repo, None, entries, _differences(vault_root, entries),
                       BASELINE_MESSAGE, SERVICE_AUTHOR, force=True)
        if made is not None:
            _advance(repo, None, made[0].id)  # False: the other process won; same baseline
    except Exception as e:
        log.warning("vault history unavailable: %s", e)
        _set_error(vault_root, str(e))


def before_write(vault_root: Path, paths: Iterable[Path | str]) -> Optional[str]:
    """Commit `paths` as they are on disk, before a write changes them. The
    commit record() makes afterwards holds only what that write changed, so a
    hand edit still sitting in the file would otherwise be overwritten with no
    commit of its own. The first call also makes the baseline. Reads only
    `paths`, so it is cheap; a file that is up to date adds no commit. Returns
    the short hash of the commit it made, or None. Never raises."""
    if not enabled():
        return None
    vault_root = Path(vault_root)
    try:
        if not vault_root.is_dir():
            return None
        repo = _open(vault_root, create=True)
        head, _ = _head(repo)
        if head is None:
            ensure_baseline(vault_root)
            return None
        specs = _relative(vault_root, paths)
        for attempt in range(_RACE_ATTEMPTS):
            if attempt:
                time.sleep(_RACE_WAIT_SECONDS)
            head, entries = _head(repo)
            if head is None:
                return None
            joined = _merge_incoming(repo, vault_root, head, entries, lambda old, new: _advance(repo, old, new))
            if joined is None:
                continue
            head, entries = joined
            changes = _differences(vault_root, entries, only=specs)
            made = _commit(repo, head, entries, changes,
                           _outside_message(repo, entries, changes), SERVICE_AUTHOR)
            if made is None:
                return None
            if _advance(repo, head, made[0].id):
                return _short(made[0].id)
    except Exception as e:
        log.warning("vault history unavailable: %s", e)
        _set_error(vault_root, str(e))
    return None


def merge_base_text(vault_root: Path, path: Path | str) -> Optional[str]:
    """The text of `path` where this computer's line and another computer's line
    forked: the version both edits started from. When several computers forked at
    different points, the newest fork. None when history holds no such version
    (the file is new on both lines, or history is off). Never raises."""
    if not enabled() or not is_repo(Path(vault_root)):
        return None
    try:
        repo = _open(Path(vault_root))
        key = _spec(Path(vault_root), path)
        head, _ = _head(repo)
        if head is None:
            return None
        own = computer_id().encode("ascii")
        found = []
        for name, tip in _tips(repo).items():
            if name == own or tip == head:
                continue
            for base in find_merge_base(repo, [head, tip]):
                text = _text_at(repo, base, key)
                if text is not None:
                    found.append((repo.object_store[base].commit_time, text))
        return max(found, key=lambda f: f[0])[1] if found else None
    except Exception as e:
        log.warning("vault history unreadable: %s", e)
        return None


def snapshot_outside(vault_root: Path, paths: Optional[Iterable[Path | str]] = None) -> Optional[str]:
    """Record edits made outside Loci (Obsidian, a text editor, a sync tool) as
    one commit, without waiting for the next Loci write. `paths` limits the
    comparison to those files, which is cheap; None compares the whole vault.
    Files that arrived from another computer are joined as "Synced from …"
    first, as in record(). Returns the short hash of the newest commit made, or
    None when nothing changed, history is off, or the vault has no history yet
    (the first Loci write makes the baseline). Never raises."""
    if not enabled():
        return None
    vault_root = Path(vault_root)
    try:
        if not vault_root.is_dir() or not is_repo(vault_root):
            return None
        specs = None if paths is None else _relative(vault_root, paths)
        if specs is not None and not specs:
            return None
        repo = _open(vault_root)
        for attempt in range(_RACE_ATTEMPTS):
            if attempt:
                time.sleep(_RACE_WAIT_SECONDS)
            head, entries = _head(repo)
            if head is None:
                return None
            newest = None
            joined = _merge_incoming(repo, vault_root, head, entries, lambda old, new: _advance(repo, old, new))
            if joined is None:
                continue
            if joined[0] != head:
                newest = joined[0]
            head, entries = joined
            changes = _differences(vault_root, entries, only=specs)
            made = _commit(repo, head, entries, changes,
                           f"{_outside_message(repo, entries, changes)}\n\nSource: watcher", SERVICE_AUTHOR)
            if made is None:
                return _short(newest) if newest else None
            if _advance(repo, head, made[0].id):
                _clear_error(vault_root)
                return _short(made[0].id)
    except Exception as e:
        log.warning("vault history unavailable: %s", e)
        _set_error(vault_root, str(e))
    return None


def history(
    vault_root: Path,
    path: Path | str,
    limit: int = 50,
    also: Iterable[Path | str] = (),
    uid: Optional[str] = None,
) -> list[dict]:
    """Commits that touched `path` or any of `also` (the other paths one note has
    had, after a rename), on every computer's branch together, newest
    first: [{commit, author, date, subject}]. Raises HistoryError when the vault has no
    store; an empty list means the store has no commit for the path.

    With `also` and `uid`, a commit counts only when the file it touched held
    that uid, before or after the commit. Another note that later took an old
    file name is then not part of this note's history.

    COST, and the cheaper option if it matters: this check reads up to two files
    per path per commit, and it needs every commit that touched one of the paths
    (the limit applies after the check). It runs only for a note that has more
    than one path. If it proves too slow on a large vault, switch to option B:
    keep each old path only up to the commit where another uid first takes it,
    and skip the per-commit read."""
    _require_repo(Path(vault_root))
    try:
        vault_root = Path(vault_root)
        repo = _open(vault_root)
        specs = _relative(vault_root, [path, *also])
        if repo is None or not specs:
            return []
        tips = _tips(repo)
        if not tips:
            return []
        out = []
        check = bool(uid) and len(specs) > 1
        entries, _ = _walk(repo, list(tips.values()), paths=specs,
                           **({} if check else {"max_entries": int(limit)}))
        for entry in entries:
            c = entry.commit
            if check and not _carries_uid(repo, c, specs, uid):
                continue
            if len(out) >= int(limit):
                break
            when = datetime.fromtimestamp(c.author_time, timezone(timedelta(seconds=c.author_timezone)))
            out.append({
                "commit": c.id.decode("ascii"),
                "author": c.author.partition(b" <")[0].decode("utf-8", "replace"),
                "date": when.isoformat(),
                "subject": c.message.decode("utf-8", "replace").splitlines()[0] if c.message else "",
            })
        return out
    except Exception as e:
        log.warning("vault history unreadable: %s", e)
        _set_error(vault_root, str(e))
        return []


def _carries_uid(repo: Repo, commit: Commit, keys: list[bytes], uid: str) -> bool:
    """True when `commit` changed one of `keys` and that file held `uid` right
    before or right after: the commit changed this note, not another note at the
    same path. A key the commit left as it was does not count."""
    parent = commit.parents[0] if commit.parents else None
    for key in keys:
        after = _bytes_at(repo, commit.id, key)
        before = _bytes_at(repo, parent, key) if parent is not None else None
        if after == before:
            continue
        for data in (after, before):
            if data is not None and _uid_of(data) == uid:
                return True
    return False


def uid_at_path(vault_root: Path, path: Path | str) -> Optional[str]:
    """The uid of the note that last lived at `path`, for a path whose file is
    gone (renamed, moved or deleted). None when history never saw a note there."""
    _require_repo(Path(vault_root))
    repo = _open(Path(vault_root))
    key = _spec(Path(vault_root), path)
    tips = _tips(repo) if repo is not None else {}
    if not tips:
        return None
    entries, _ = _walk(repo, list(tips.values()), paths=[key], max_entries=1)
    if not entries:
        return None
    commit = entries[0].commit
    for at in (commit.id, commit.parents[0] if commit.parents else None):
        data = _bytes_at(repo, at, key) if at is not None else None
        uid = _uid_of(data) if data is not None else None
        if uid:
            return uid
    return None


# ---------------------------------------------------------------------------
# Reading and restoring
# ---------------------------------------------------------------------------

def _require_repo(vault_root: Path) -> None:
    if not enabled():
        raise HistoryError("Vault history is turned off (LOCI_VAULT_HISTORY=0).")
    if not is_repo(vault_root):
        raise HistoryError("The vault has no history yet: nothing has been written since tracking began.")


# Every commit id reachable from any branch, per vault: built by one walk and
# then only extended by the commits added since, so a short hash never walks the
# history again. The sync HTTP endpoints run in a thread pool, so the lock guards it.
_commit_ids_cache: dict[str, tuple[tuple[bytes, ...], list[bytes]]] = {}
_commit_ids_lock = threading.Lock()
_CACHE_VAULTS = 8       # vaults a process keeps cached; the oldest is dropped past this


def _remember(cache: dict, key: str, value) -> None:
    """Store `value` under `key`, dropping the longest-cached vault once more than
    _CACHE_VAULTS are held, so a process that switches vault roots does not keep
    every history it has ever read."""
    cache.pop(key, None)
    cache[key] = value
    while len(cache) > _CACHE_VAULTS:
        del cache[next(iter(cache))]


def _descends(repo: Repo, old: bytes, new: bytes) -> bool:
    """True when `new` builds on `old`. False when `old` is not in the store at
    all, as after the history was deleted or re-created: the caller then starts
    from a fresh walk."""
    try:
        return can_fast_forward(repo, old, new)
    except KeyError:
        return False


# dulwich's walker raises MissingCommitError for a parent that is not in the store;
# its other lookups raise KeyError.
_MISSING = (KeyError, MissingCommitError)


def _walk(repo: Repo, include: list[bytes], **kwargs) -> tuple[list, bool]:
    """(walk entries, complete) for the commits reachable from `include`. A sync
    tool can bring a branch and its newest commit before the older commits, so a
    walk can hit a parent that is not in the store yet. The walk then covers only
    the tips whose whole line is present, and `complete` is False: the caller
    must not cache that answer, because the same tips will give a fuller one once
    the sync ends."""
    try:
        return list(repo.get_walker(include=include, **kwargs)), True
    except _MISSING:
        pass
    sound = []
    for tip in include:
        try:
            for _ in repo.get_walker(include=[tip]):
                pass
            sound.append(tip)
        except _MISSING:
            continue
    if not sound:
        return [], False
    try:
        return list(repo.get_walker(include=sound, **kwargs)), False
    except _MISSING:
        return [], False


def _tip_key(repo: Repo) -> tuple[bytes, ...]:
    return tuple(sorted(set(_tips(repo).values())))


def _commit_ids(repo: Repo, tips: tuple[bytes, ...]) -> list[bytes]:
    key = str(repo.path)
    with _commit_ids_lock:
        known = _commit_ids_cache.get(key)
        if known is not None and known[0] == tips:
            return known[1]
        if known is not None and all(old in repo.object_store for old in known[0]):
            # Everything reachable from the old tips is already in the list, so
            # only what the new tips add is walked.
            entries, complete = _walk(repo, list(tips), exclude=list(known[0]))
            ids = known[1] + [e.commit.id for e in entries]
        else:
            entries, complete = _walk(repo, list(tips))
            ids = [e.commit.id for e in entries]
        if complete:
            _remember(_commit_ids_cache, key, (tips, ids))
        return ids


def _resolve(repo: Repo, commit: str) -> bytes:
    """The commit id a reference names: a hash or hash prefix (found on any
    computer's branch), or HEAD (this computer's branch), then `~n` steps back
    along the first parent. Raises HistoryError for anything else,
    and for a prefix that names more than one commit."""
    ref = (commit or "").strip().lower()
    if ref.startswith("head"):
        ref = "HEAD" + ref[4:]
    if not _REV_RE.fullmatch(ref):
        raise HistoryError(f"Not a commit reference: {commit!r}. Use a hash from history_vault, "
                           "e.g. 'a1b2c3d' or 'a1b2c3d~1'.")
    base, _, back = ref.partition("~")
    head, _ = _head(repo)
    if head is None:
        raise HistoryError("The vault has no history yet: nothing has been written since tracking began.")
    if base == "HEAD":
        found = head
    elif len(base) == 40:
        found = base.encode("ascii")
        if found not in repo.object_store or not isinstance(repo[found], Commit):
            raise HistoryError(f"No commit {base!r} in the history. Use a hash from history_vault.")
    else:
        matches = [c for c in _commit_ids(repo, _tip_key(repo)) if c.decode("ascii").startswith(base)]
        if not matches:
            raise HistoryError(f"No commit {base!r} in the history. Use a hash from history_vault.")
        if len(matches) > 1:
            raise HistoryError(f"{base!r} names {len(matches)} commits. Use more characters of the hash.")
        found = matches[0]
    for _ in range(int(back or 0)):
        parents = repo[found].parents
        if not parents:
            raise HistoryError(f"{ref} goes back past the first commit.")
        found = parents[0]
    return found


def _bytes_at(repo: Repo, commit_id: bytes, key: bytes) -> Optional[bytes]:
    try:
        _, sha = tree_lookup_path(repo.object_store.__getitem__, repo[commit_id].tree, key)
    except KeyError:
        return None
    return repo[sha].data


def _text_at(repo: Repo, commit_id: bytes, key: bytes) -> Optional[str]:
    data = _bytes_at(repo, commit_id, key)
    return None if data is None else data.decode("utf-8", "replace")


def _spec(vault_root: Path, path: Path | str) -> bytes:
    specs = _relative(vault_root, [path])
    if not specs:
        raise HistoryError(f"{path} is outside the vault.")
    return specs[0]


# uid -> (vault-relative path of the file that last carried it, commit time), per
# vault, built by one walk of the history and then only extended: a lookup never
# walks again. The time is kept because a line that arrives from another computer
# can hold commits older than ones already indexed, and the newest must win.
# The sync HTTP endpoints run in a thread pool, so the lock guards every use.
_UID_LINE = re.compile(rb"(?m)^uid:[ \t]*['\"]?([^\s'\"]+)['\"]?[ \t\r]*$")
_uid_index: dict[str, tuple[tuple[bytes, ...], dict[str, tuple[str, int, frozenset[str]]]]] = {}
_uid_index_lock = threading.Lock()


def _uid_entry(vault_root: Path, uid: str) -> Optional[tuple[str, int, frozenset[str]]]:
    """(newest path, its commit time, every path) for `uid`, or None."""
    _require_repo(vault_root)
    repo = _open(vault_root)
    tips = _tip_key(repo)
    if not tips:
        return None
    root = str(Path(vault_root))
    with _uid_index_lock:
        known = _uid_index.get(root)
        if known is None or known[0] != tips:
            index, complete = _extend_uid_index(repo, tips, known)
            if not complete:    # part of a line is still arriving: answer, but do not keep it
                return index.get(uid)
            _remember(_uid_index, root, (tips, index))
        return _uid_index[root][1].get(uid)


def find_path(vault_root: Path, uid: str) -> Optional[str]:
    """Vault-relative path of the file that last carried `uid`, for a node whose
    file is gone. None when history never saw it."""
    found = _uid_entry(vault_root, uid)
    return found[0] if found else None


def paths_of(vault_root: Path, uid: str) -> list[str]:
    """Every vault-relative path a node has had, the newest first. A note that
    was renamed or moved has more than one; the history of the node is the
    commits of all of them."""
    found = _uid_entry(vault_root, uid)
    if not found:
        return []
    return [found[0]] + sorted(found[2] - {found[0]})


def _extend_uid_index(
    repo: Repo,
    tips: tuple[bytes, ...],
    known: Optional[tuple[tuple[bytes, ...], dict[str, tuple[str, int, frozenset[str]]]]],
) -> tuple[dict[str, tuple[str, int, frozenset[str]]], bool]:
    """(index, complete) as of `tips`: `known` plus the commits added since it was
    built, or a fresh walk when the old tips are no longer all in the store.
    `complete` is False when part of a line has not arrived yet."""
    if known is not None and all(old in repo.object_store for old in known[0]):
        index = dict(known[1])
        entries, complete = _walk(repo, list(tips), exclude=list(known[0]))
    else:
        index = {}
        entries, complete = _walk(repo, list(tips))
    # Newest first, so the first commit to name a uid owns it among the commits of
    # this walk. Against what is already indexed, only a commit that is not older
    # takes over.
    # Every path a uid appears at is kept, for the history of a renamed note.
    seen: set[str] = set()
    for entry in entries:
        when = entry.commit.commit_time
        for uid, paths in _uids_in(repo, entry.commit).items():
            current = index.get(uid)
            held = (current[2] if current else frozenset()) | frozenset(paths)
            if uid not in seen:
                seen.add(uid)
                if current is None or when >= current[1]:
                    index[uid] = (paths[0], when, held)
                    continue
            if current is not None:
                index[uid] = (current[0], current[1], held)
    return index, complete


def _uids_in(repo: Repo, commit: Commit) -> dict[str, list[str]]:
    parent_tree = repo[commit.parents[0]].tree if commit.parents else None
    found: dict[str, list[str]] = {}
    changes = list(tree_changes(repo.object_store, parent_tree, commit.tree))
    # Where the file is now before where it was: a move shows as a delete and an
    # add, and the delete can sort first.
    for side in [c.new for c in changes] + [c.old for c in changes]:
        if side and side.sha and side.path.endswith(b".md"):
            # Only the frontmatter: a note that quotes a "uid:" line in its
            # body must not be taken for the node that owns it.
            header, _ = split_frontmatter(repo[side.sha].data.decode("utf-8", "replace"))
            match = header and _UID_LINE.search(header.encode("utf-8"))
            if match:
                where = found.setdefault(match.group(1).decode("utf-8", "replace"), [])
                name = side.path.decode("utf-8", "surrogateescape")
                if name not in where:
                    where.append(name)
    return found


def show(vault_root: Path, commit: str, path: Path | str) -> str:
    """The text of `path` as it was right after `commit`."""
    _require_repo(vault_root)
    repo = _open(vault_root)
    commit_id = _resolve(repo, commit)
    key = _spec(vault_root, path)
    text = _text_at(repo, commit_id, key)
    if text is None:
        name = key.decode("utf-8", "replace")
        raise HistoryError(
            f"{name} does not exist at {commit}. If {commit} is the commit that deleted it, "
            f"use '{commit}~1' for the version before."
        )
    return text


def show_bytes(vault_root: Path, commit: str, path: Path | str) -> bytes:
    """The exact bytes of `path` right after `commit`: what a restore writes
    back, so a file that is not valid UTF-8 returns unchanged."""
    _require_repo(vault_root)
    repo = _open(vault_root)
    commit_id = _resolve(repo, commit)
    key = _spec(vault_root, path)
    data = _bytes_at(repo, commit_id, key)
    if data is None:
        raise HistoryError(f"{key.decode('utf-8', 'replace')} does not exist at {commit}.")
    return data


def diff(vault_root: Path, commit: str, path: Path | str) -> str:
    """The change `commit` made to `path`, as a unified diff."""
    _require_repo(vault_root)
    repo = _open(vault_root)
    commit_id = _resolve(repo, commit)
    key = _spec(vault_root, path)
    name = key.decode("utf-8", "replace")
    parents = repo[commit_id].parents
    old = _text_at(repo, parents[0], key) if parents else None
    new = _text_at(repo, commit_id, key)
    if old == new:
        raise HistoryError(f"{commit} did not change {name}.")
    c = repo[commit_id]
    when = datetime.fromtimestamp(c.author_time, timezone(timedelta(seconds=c.author_timezone)))
    lines_of_message = c.message.decode("utf-8", "replace").splitlines()
    header = f"{_short(commit_id)} {c.author.partition(b' <')[0].decode('utf-8', 'replace')} " \
             f"{when.isoformat()}\n{lines_of_message[0] if lines_of_message else ''}\n\n"
    lines = difflib.unified_diff(
        (old or "").splitlines(), (new or "").splitlines(),
        fromfile=f"a/{name}" if old is not None else "/dev/null",
        tofile=f"b/{name}" if new is not None else "/dev/null",
        lineterm="",
    )
    body = "\n".join(lines)
    if not body:
        # Same lines, different bytes: a final newline or the line endings.
        body = f"(no line changed: only the final newline or the line endings differ in {name})"
    return header + body + "\n"


LOCK_TIMEOUT_S = 10.0
_lock_held = threading.local()      # roots this thread already holds, so a nested take is a no-op


@contextmanager
def write_lock(vault_root: Path, required: bool = False):
    """Hold the vault's write lock, across processes. The MCP server and the UI
    backend are separate processes, and two of them writing or undoing at once
    would each overwrite the other's files.

    Every write takes it (see `_serialized` in api.py). Undo and restore also
    re-check HEAD under it. It waits up to LOCK_TIMEOUT_S, then raises
    HistoryError: a hung holder must not pin a request thread forever.

    It is re-entrant within a thread. It is a no-op while history is off or while
    the vault has no history store yet. When the lock file cannot be opened a
    plain write goes on without it, with a warning; with `required=True`, which
    undo and restore pass, HistoryError is raised instead, because an undo that
    runs unlocked can overwrite another process's write.

    It uses `filelock`, which takes flock on macOS and Linux and a byte-range lock
    on Windows, so the same code locks on every platform. Windows is not a tested
    platform. Things to know:
      - The lock file `.loci/<computer>.undo.lock` is kept after release
        (`preserve_lock_file=True`), on every platform: one small file per
        computer, reused, never re-created while another process opens it. If a
        user deletes it during a write, a second writer could lock a new file.
      - A filesystem that cannot lock at all (some network mounts) makes filelock
        raise NotImplementedError; with `preserve_lock_file` it does not fall back
        to a soft lock file that a crash could leave behind. The error is handled
        like a lock file that cannot be opened: a plain write goes on unlocked;
        undo and restore refuse."""
    held = _lock_held.__dict__.setdefault("roots", set())
    key = str(Path(vault_root))
    if key in held or not enabled() or not is_repo(vault_root):
        yield
        return
    lock = FileLock(str(Path(vault_root) / ".loci" / f"{computer_id()}.undo.lock"), preserve_lock_file=True)
    try:
        lock.acquire(timeout=LOCK_TIMEOUT_S, poll_interval=0.05)
    except Timeout:
        raise HistoryError(
            "The vault is busy: another write, undo or restore is still running. Nothing was changed. Try again in a moment."
        ) from None
    except (OSError, NotImplementedError) as e:    # no lock file, or a filesystem that cannot lock: a plain write goes on
        if required:
            raise HistoryError(
                f"The vault's write lock cannot be opened ({e}), so the change was not made."
            ) from e
        log.warning("write lock unavailable, continuing without it: %s", e)
        yield
        return
    held.add(key)
    try:
        yield
    finally:
        held.discard(key)
        try:
            lock.release()
        except OSError as e:    # must not hide the error of the write itself
            log.warning("write lock release failed: %s", e)


def snapshot_external(vault_root: Path, paths: Iterable[Path | str]) -> Optional[str]:
    """Commit uncommitted changes to `paths` (edits made outside Loci) before a
    restore overwrites them, so the restore itself loses nothing. Returns the
    commit's short hash, or None when the files were up to date."""
    return before_write(vault_root, paths)


def head_short(vault_root: Path) -> Optional[str]:
    """Short hash of the newest commit, None when there is none."""
    _require_repo(vault_root)
    head, _ = _head(_open(vault_root))
    return _short(head) if head else None


def head_id(vault_root: Path) -> Optional[str]:
    """Full hash of the newest commit, None when there is none."""
    _require_repo(vault_root)
    head, _ = _head(_open(vault_root))
    return head.decode("ascii") if head else None


def head_changes(vault_root: Path) -> tuple[str, str, list[tuple[str, str]]]:
    """(short hash, subject, [(status, path)]) for the newest commit, with status
    A, M or D. Raises when that commit is the baseline or the first commit:
    there is nothing before it."""
    _require_repo(vault_root)
    repo = _open(vault_root)
    head, _ = _head(repo)
    if head is None:
        raise HistoryError("The vault has no history yet: nothing has been written since tracking began.")
    commit = repo[head]
    subject = commit.message.decode("utf-8", "replace").splitlines()[0] if commit.message else ""
    if subject.startswith("Baseline:") or not commit.parents:
        raise HistoryError("The newest commit is the baseline. There is no earlier change to undo.")
    if subject == OUTSIDE_MESSAGE or subject.startswith(RENAMED_PREFIX):
        raise HistoryError(
            f"The newest commit ({_short(head)}) holds edits made outside Loci, not a Loci write. "
            "Undoing it would remove those edits. Use history_vault and restore_vault on the one node instead."
        )
    if subject.startswith(SYNCED_MESSAGE):
        raise HistoryError(
            f"The newest commit ({_short(head)}) holds changes that arrived from another computer, not a Loci write. "
            "Undoing it would remove that computer's edits. Use history_vault and restore_vault on the one node instead."
        )
    status = {"add": "A", "delete": "D", "modify": "M"}
    rows = [
        (status.get(change.type, "M"), ((change.new and change.new.path) or change.old.path).decode("utf-8", "surrogateescape"))
        for change in tree_changes(repo.object_store, repo[commit.parents[0]].tree, commit.tree)
    ]
    return _short(head), subject, rows
