"""
vault_history.py

Change history for the vault, kept in a Git-format repository that Loci owns.

The repository lives at vault_root/.loci/history, apart from any `.git` the
user keeps in the vault, and is read and written with dulwich, a pure-Python
Git library. Nothing here runs the `git` command, so the history works on a
machine that has no Git installed. The repository has no index and no working
tree of its own: a commit is built straight from the files on disk, so
`git --git-dir vault/.loci/history log` and `show` read it, and a second
process can write beside the first without an index lock.

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
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from dulwich.diff_tree import tree_changes
from dulwich.file import FileLocked
from dulwich.index import commit_tree
from dulwich.object_store import iter_tree_contents, tree_lookup_path
from dulwich.objects import ZERO_SHA, Blob, Commit
from dulwich.repo import Repo

from loci.tools.frontmatter import split_frontmatter

log = logging.getLogger(__name__)

SERVICE_AUTHOR = "loci <loci@localhost>"
HISTORY_DIR = Path(".loci") / "history"
BRANCH = b"refs/heads/main"
BASELINE_MESSAGE = "Baseline: vault before history tracking"
OUTSIDE_MESSAGE = "Changes made outside Loci"

# The MCP and UI servers are separate processes that can commit to the same
# repository. The branch is moved with a compare-and-swap, so the loser of a
# race rebuilds its commit on the winner's and tries again.
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
# STATUS_FILE, where the other one reads it; this dict is the fallback for a
# disk that will not take that file either.
_last_error: dict[str, str] = {}
STATUS_FILE = Path(".loci") / "history-status.json"


# A commit as the agent names it: a hash, optionally stepped back ("abc123~1" is
# the version before abc123 — how a deleted file is reached), or HEAD.
_REV_RE = re.compile(r"(?:[0-9a-f]{4,40}|HEAD)(?:~\d{1,4})?")


class HistoryError(Exception):
    """A history request that cannot be answered: no store, bad commit, no such
    version. The message is for the agent to read."""


def _short(commit_id: bytes) -> str:
    return commit_id.decode("ascii")[:7]


def _set_error(vault_root: Path, reason: str) -> None:
    """Show `reason` to every process through STATUS_FILE. Only when that file
    cannot be written does this process keep the reason to itself: a copy kept
    beside a working file would outlive the other process clearing it."""
    root = str(Path(vault_root).resolve())
    try:
        path = Path(vault_root) / STATUS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"error": reason}), encoding="utf-8")
        _last_error.pop(root, None)
    except OSError:
        _last_error[root] = reason


def _clear_error(vault_root: Path) -> None:
    _last_error.pop(str(Path(vault_root).resolve()), None)
    try:
        (Path(vault_root) / STATUS_FILE).unlink()
    except OSError:
        pass


def _read_error(vault_root: Path) -> Optional[str]:
    try:
        reason = json.loads((Path(vault_root) / STATUS_FILE).read_text(encoding="utf-8")).get("error")
        if reason:
            return reason
    except (OSError, ValueError, AttributeError):
        pass
    return _last_error.get(str(Path(vault_root).resolve()))


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
        # HEAD on "master", and `git log` on the store would show nothing.
        names, _ = repo.refs.follow(b"HEAD")
        if names[-1] != BRANCH:
            repo.refs.set_symbolic_ref(b"HEAD", BRANCH)
        return repo
    if not create:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        repo = Repo.init_bare(str(path), mkdir=True)
    except FileExistsError:
        # The other process (MCP and UI both write) created the store first.
        return Repo(str(path))
    repo.refs.set_symbolic_ref(b"HEAD", BRANCH)
    return repo


def _eligible(rel: Path) -> bool:
    return not any(part in _SKIP_DIRS for part in rel.parts) and not any(
        fnmatch.fnmatch(rel.name, pattern) for pattern in _SKIP_FILES
    )


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


def _head(repo: Repo) -> tuple[Optional[bytes], dict[bytes, tuple[int, bytes]]]:
    """(commit id, {key: (mode, blob id)}) for the branch, or (None, {}) before
    the first commit."""
    try:
        head = repo.refs[BRANCH]
    except KeyError:
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
) -> Optional[tuple[Commit, dict[bytes, tuple[int, bytes]]]]:
    """Commit `entries` with `changes` applied. None when that is the tree the
    parent already has (nothing to commit), unless `force` asks for it anyway."""
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
    commit.parents = [parent] if parent is not None else []
    commit.author = commit.committer = f"{name} <{email}>".encode("utf-8")
    commit.author_time = commit.commit_time = now
    commit.author_timezone = commit.commit_timezone = offset
    commit.encoding = b"UTF-8"
    commit.message = message.encode("utf-8")
    repo.object_store.add_object(commit)
    return commit, new


def _advance(repo: Repo, old: Optional[bytes], new: bytes) -> bool:
    """Move the branch from `old` to `new`. False when another process moved it
    first. Raises FileLocked when something holds the branch lock."""
    # dulwich skips the comparison for None; ZERO_SHA means "must not exist
    # yet", so two first commits cannot both win.
    return repo.refs.set_if_equals(BRANCH, ZERO_SHA if old is None else old, new)


def record(
    vault_root: Path,
    message: str,
    paths: Iterable[Path | str],
    *,
    author: Optional[str] = None,
    source: Optional[str] = None,
) -> bool:
    """Commit `paths` (files written or deleted) with `message`, after one
    commit for anything else that changed outside Loci. Returns the new commit's
    short hash, or None when no commit was made (history off, nothing changed,
    or a failure). Never raises."""
    if not enabled():
        return None
    vault_root = Path(vault_root)
    try:
        specs = _relative(vault_root, paths)
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
                               BASELINE_MESSAGE if head is None else OUTSIDE_MESSAGE,
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
            lock = history_dir(vault_root) / "refs" / "heads" / "main.lock"
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
            made = _commit(repo, head, entries, _differences(vault_root, entries, only=specs),
                           OUTSIDE_MESSAGE, SERVICE_AUTHOR)
            if made is None:
                return None
            if _advance(repo, head, made[0].id):
                return _short(made[0].id)
    except Exception as e:
        log.warning("vault history unavailable: %s", e)
        _set_error(vault_root, str(e))
    return None


def history(vault_root: Path, path: Path | str, limit: int = 50) -> list[dict]:
    """Commits that touched `path`, newest first:
    [{commit, author, date, subject}]. Raises HistoryError when the vault has no
    store; an empty list means the store has no commit for the path."""
    _require_repo(Path(vault_root))
    try:
        vault_root = Path(vault_root)
        repo = _open(vault_root)
        specs = _relative(vault_root, [path])
        if repo is None or not specs:
            return []
        head, _ = _head(repo)
        if head is None:
            return []
        out = []
        for entry in repo.get_walker(include=[head], paths=[specs[0]], max_entries=int(limit)):
            c = entry.commit
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


# ---------------------------------------------------------------------------
# Reading and restoring
# ---------------------------------------------------------------------------

def _require_repo(vault_root: Path) -> None:
    if not enabled():
        raise HistoryError("Vault history is turned off (LOCI_VAULT_HISTORY=0).")
    if not is_repo(vault_root):
        raise HistoryError("The vault has no history yet: nothing has been written since tracking began.")


def _resolve(repo: Repo, commit: str) -> bytes:
    """The commit id a reference names: a hash or hash prefix, or HEAD, then `~n`
    steps back along the first parent. Raises HistoryError for anything else,
    and for a prefix that names more than one commit."""
    ref = (commit or "").strip().lower()
    if ref.startswith("head"):
        ref = "HEAD" + ref[4:]
    if not _REV_RE.fullmatch(ref):
        raise HistoryError(f"Not a commit reference: {commit!r}. Use a hash from history_vault, "
                           "e.g. 'a1b2c3d' or 'a1b2c3d~1'.")
    base, _, back = ref.partition("~")
    try:
        head = repo.refs[BRANCH]
    except KeyError:
        raise HistoryError("The vault has no history yet: nothing has been written since tracking began.")
    if base == "HEAD":
        found = head
    elif len(base) == 40:
        found = base.encode("ascii")
        if found not in repo.object_store or not isinstance(repo[found], Commit):
            raise HistoryError(f"No commit {base!r} in the history. Use a hash from history_vault.")
    else:
        matches = [e.commit.id for e in repo.get_walker(include=[head])
                   if e.commit.id.decode("ascii").startswith(base)]
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


def _text_at(repo: Repo, commit_id: bytes, key: bytes) -> Optional[str]:
    try:
        _, sha = tree_lookup_path(repo.object_store.__getitem__, repo[commit_id].tree, key)
    except KeyError:
        return None
    return repo[sha].data.decode("utf-8", "replace")


def _spec(vault_root: Path, path: Path | str) -> bytes:
    specs = _relative(vault_root, [path])
    if not specs:
        raise HistoryError(f"{path} is outside the vault.")
    return specs[0]


_find_cache: dict = {}


def find_path(vault_root: Path, uid: str) -> Optional[str]:
    """Vault-relative path of the file that last carried `uid`, for a node whose
    file is gone. None when history never saw it."""
    _require_repo(vault_root)
    repo = _open(vault_root)
    head, _ = _head(repo)
    if head is None:
        return None
    # Every write moves HEAD, so a result is good exactly as long as HEAD is the
    # same: a uid that misses on disk is not re-walked through the whole history.
    key = (str(Path(vault_root)), head)
    if key in _find_cache and uid in _find_cache[key]:
        return _find_cache[key][uid]
    if len(_find_cache) > 8:
        _find_cache.clear()
    result = _scan_for_uid(repo, head, uid)
    _find_cache.setdefault(key, {})[uid] = result
    return result


def _scan_for_uid(repo, head, uid: str) -> Optional[str]:
    # A uid of digits only is stored quoted (uid: '12345678'), so allow quotes.
    needle = re.compile(rb"(?m)^uid:[ \t]*['\"]?" + re.escape(uid.encode()) + rb"['\"]?[ \t]*$")
    for entry in repo.get_walker(include=[head]):
        commit = entry.commit
        parent_tree = repo[commit.parents[0]].tree if commit.parents else None
        for change in tree_changes(repo.object_store, parent_tree, commit.tree):
            for side in (change.new, change.old):
                if side and side.sha and side.path.endswith(b".md"):
                    # Only the frontmatter: a note that quotes a "uid:" line in its
                    # body must not be taken for the node that owns it.
                    header, _ = split_frontmatter(repo[side.sha].data.decode("utf-8", "replace"))
                    if header and needle.search(header.encode("utf-8")):
                        return side.path.decode("utf-8", "surrogateescape")
    return None


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
    if subject == OUTSIDE_MESSAGE:
        raise HistoryError(
            f"The newest commit ({_short(head)}) holds edits made outside Loci, not a Loci write. "
            "Undoing it would remove those edits. Use history_vault and restore_vault on the one node instead."
        )
    status = {"add": "A", "delete": "D", "modify": "M"}
    rows = [
        (status.get(change.type, "M"), ((change.new and change.new.path) or change.old.path).decode("utf-8", "surrogateescape"))
        for change in tree_changes(repo.object_store, repo[commit.parents[0]].tree, commit.tree)
    ]
    return _short(head), subject, rows
