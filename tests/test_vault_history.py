"""
Vault change history: every API write is one commit in the history store at
vault_root/.loci/history, a Git-format repository that dulwich reads and writes.
"""

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
from dulwich.diff_tree import tree_changes
from dulwich.object_store import tree_lookup_path
from dulwich.repo import Repo

from loci import api
from loci.tools import nx_graph, vault_history


@pytest.fixture(autouse=True)
def history_on(monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")
    vault_history.set_source("api")
    vault_history._stat_cache.clear()
    vault_history._last_error.clear()
    vault_history._last_walk.clear()
    yield
    vault_history.set_source("api")   # a test that names another channel must not leak it


def save(title):
    return api.save(
        type="document", title=title, body="hello",
        extra_fields={"status": "draft", "subtype": "note"},
    )


def repo(vault):
    return Repo(str(vault_history.history_dir(vault)))


def commits(vault):
    """Every commit, newest first."""
    r = repo(vault)
    return [e.commit for e in r.get_walker(include=[r.head()])]


def log(vault):
    """'author|subject' for every commit, newest first."""
    return [
        f"{c.author.partition(b' <')[0].decode()}|{c.message.decode().splitlines()[0]}"
        for c in commits(vault)
    ]


def subjects(vault):
    return [line.split("|", 1)[1] for line in log(vault)]


def files_changed(vault, commit):
    r = repo(vault)
    parent_tree = r[commit.parents[0]].tree if commit.parents else None
    return sorted(
        (c.new.path or c.old.path).decode() for c in tree_changes(r.object_store, parent_tree, commit.tree)
    )


def blob_at(vault, commit, rel):
    r = repo(vault)
    _, sha = tree_lookup_path(r.object_store.__getitem__, commit.tree, rel.encode())
    return r[sha].data.decode()


def in_head(vault, rel):
    r = repo(vault)
    try:
        tree_lookup_path(r.object_store.__getitem__, r[r.head()].tree, rel.encode())
        return True
    except KeyError:
        return False


def rel(vault, saved):
    return str(Path(saved["path"]).relative_to(vault))


def test_first_write_creates_the_store_with_a_baseline(tmp_vault):
    save("History One")
    assert vault_history.history_dir(tmp_vault).is_dir()
    assert not (tmp_vault / ".git").exists()
    assert not (tmp_vault / ".gitignore").exists()
    assert subjects(tmp_vault)[0].startswith("Add document: History One")
    assert subjects(tmp_vault)[-1].startswith("Baseline")


def test_history_needs_no_git_command(tmp_vault, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))     # an empty directory: no git on the PATH
    assert shutil.which("git") is None
    result = save("History One")
    assert result["uid"]
    assert subjects(tmp_vault)[0].startswith("Add document: History One")


def test_save_commits_only_the_written_file(tmp_vault):
    save("History One")
    (tmp_vault / "stray.md").write_text("not written by loci")
    result = save("History Two")
    assert files_changed(tmp_vault, commits(tmp_vault)[0]) == [rel(tmp_vault, result)]


def test_changes_made_outside_loci_get_their_own_commit(tmp_vault):
    first = save("History One")
    (tmp_vault / "stray.md").write_text("made by hand")
    edited = tmp_vault / rel(tmp_vault, first)
    edited.write_text(edited.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
    save("History Two")
    assert subjects(tmp_vault)[1] == "Changes made outside Loci"
    assert files_changed(tmp_vault, commits(tmp_vault)[1]) == sorted(["stray.md", rel(tmp_vault, first)])
    assert "hand edit" in blob_at(tmp_vault, commits(tmp_vault)[1], rel(tmp_vault, first))


def test_no_outside_commit_when_nothing_changed_outside(tmp_vault):
    save("History One")
    save("History Two")
    assert "Changes made outside Loci" not in subjects(tmp_vault)


def test_what_is_in_the_vault_before_the_first_write_is_the_baseline(tmp_vault):
    (tmp_vault / "old-note.md").write_text("from before")
    save("History One")
    baseline = commits(tmp_vault)[-1]
    assert baseline.message.decode().startswith("Baseline")
    assert blob_at(tmp_vault, baseline, "old-note.md") == "from before"
    assert files_changed(tmp_vault, commits(tmp_vault)[0]) != []


def test_patch_commit_shows_the_change(tmp_vault):
    saved = save("History One")
    api.patch(saved["uid"], {"summary": "A new summary"})
    newest, previous = commits(tmp_vault)[0], commits(tmp_vault)[1]
    assert subjects(tmp_vault)[0].startswith("Update History One")
    assert "summary: A new summary" in blob_at(tmp_vault, newest, rel(tmp_vault, saved))
    assert "summary: A new summary" not in blob_at(tmp_vault, previous, rel(tmp_vault, saved))


def test_delete_is_committed(tmp_vault):
    saved = save("History One")
    api.delete(saved["uid"])
    assert subjects(tmp_vault)[0].startswith("Delete History One")
    assert not in_head(tmp_vault, rel(tmp_vault, saved))


def test_default_author_is_loci_and_source_is_a_trailer(tmp_vault):
    save("History One")
    assert log(tmp_vault)[0].startswith("loci|")
    assert "Source: api" in commits(tmp_vault)[0].message.decode()
    vault_history.set_source("mcp")
    save("History Two")
    assert "Source: mcp" in commits(tmp_vault)[0].message.decode()


def test_caller_can_name_the_author(tmp_vault):
    path = tmp_vault / "note.md"
    path.write_text("x")
    assert vault_history.record(
        tmp_vault, "Edit note", [path], author="Ada <ada@example.com>"
    )
    assert log(tmp_vault)[0] == "Ada|Edit note"


def test_history_lists_commits_for_one_file(tmp_vault):
    saved = save("History One")
    api.patch(saved["uid"], {"summary": "changed"})
    entries = vault_history.history(tmp_vault, saved["path"])
    assert [e["subject"].split(" ")[0] for e in entries] == ["Update", "Add"]
    assert entries[0]["author"] == "loci"


def test_history_of_a_deleted_file_is_still_listed(tmp_vault):
    saved = save("History One")
    api.delete(saved["uid"])
    assert [e["subject"].split(" ")[0] for e in vault_history.history(tmp_vault, saved["path"])] == [
        "Delete", "Add",
    ]


def test_unchanged_patch_makes_no_extra_commit(tmp_vault):
    saved = save("History One")
    before = len(log(tmp_vault))
    assert vault_history.record(tmp_vault, "No change", [saved["path"]]) is None
    assert len(log(tmp_vault)) == before


def test_meta_and_overlay_writes_are_committed(tmp_vault):
    api.write_meta("tag-dictionary", "# tags\n")
    assert subjects(tmp_vault)[0] == "Update meta: tag-dictionary"


def test_assets_outside_the_vault_are_never_committed(tmp_vault):
    outside = tmp_vault.parent / "assets" / "x.bin"
    outside.parent.mkdir()
    outside.write_bytes(b"\0")
    assert vault_history.record(tmp_vault, "asset", [outside]) is None


def test_disabled_by_env(tmp_vault, monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "0")
    save("History One")
    assert not vault_history.history_dir(tmp_vault).exists()


def test_a_failure_does_not_fail_the_write(tmp_vault, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk is read-only")
    monkeypatch.setattr(vault_history, "_commit", boom)
    result = save("History One")
    assert result["uid"]
    assert (tmp_vault / rel(tmp_vault, result)).is_file()


def test_delete_as_the_first_history_write_keeps_the_content(tmp_vault, monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "0")
    saved = save("Doomed")                       # history is off: the store does not exist yet
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")
    api.delete(saved["uid"])
    assert subjects(tmp_vault)[0].startswith("Delete Doomed")
    assert subjects(tmp_vault)[1].startswith("Baseline")
    assert "hello" in blob_at(tmp_vault, commits(tmp_vault)[1], rel(tmp_vault, saved))


def test_delete_keeps_an_edit_made_outside_loci(tmp_vault):
    saved = save("Edited")
    path = Path(saved["path"])
    path.write_text(path.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
    api.delete(saved["uid"])
    assert "hand edit" in blob_at(tmp_vault, commits(tmp_vault)[1], rel(tmp_vault, saved))


def test_delete_of_an_up_to_date_file_adds_no_snapshot(tmp_vault):
    saved = save("Clean")
    before = len(commits(tmp_vault))
    api.delete(saved["uid"])
    assert len(commits(tmp_vault)) == before + 1


def test_an_interrupted_first_write_is_rebuilt_on_the_next_one(tmp_vault, monkeypatch):
    real = vault_history._commit
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("interrupted")
        return real(*args, **kwargs)

    monkeypatch.setattr(vault_history, "_commit", flaky)
    first = save("History One")                  # the baseline fails; the write still succeeds
    assert first["uid"]
    assert vault_history.is_repo(tmp_vault)      # the store exists but has no commits
    second = save("History Two")
    assert subjects(tmp_vault)[-1].startswith("Baseline")
    assert in_head(tmp_vault, rel(tmp_vault, first))
    assert files_changed(tmp_vault, commits(tmp_vault)[0]) == [rel(tmp_vault, second)]


def test_a_held_branch_lock_is_retried(tmp_vault, monkeypatch):
    save("History One")
    lock = vault_history.history_dir(tmp_vault) / "refs" / "heads" / "main.lock"
    lock.write_text("")
    monkeypatch.setattr(vault_history.time, "sleep", lambda s: lock.unlink(missing_ok=True))
    save("History Two")
    assert subjects(tmp_vault)[0].startswith("Add document: History Two")


def test_a_lock_that_never_clears_is_logged_and_the_write_still_succeeds(tmp_vault, monkeypatch, caplog):
    save("History One")
    lock = vault_history.history_dir(tmp_vault) / "refs" / "heads" / "main.lock"
    lock.write_text("")
    monkeypatch.setattr(vault_history.time, "sleep", lambda s: None)
    with caplog.at_level(logging.WARNING):
        result = save("History Two")
    assert result["uid"]
    assert "main.lock" in caplog.text and "delete that file" in caplog.text
    assert subjects(tmp_vault)[0].startswith("Add document: History One")
    assert vault_history.status(tmp_vault)["state"] == "error"


def test_a_write_left_out_by_a_lost_race_is_recorded_by_the_next_one(tmp_vault):
    save("History One")
    errors = []

    def writer(n):
        try:
            for i in range(4):
                path = tmp_vault / f"race-{n}-{i}.md"
                path.write_text(f"{n}-{i}")
                vault_history.record(tmp_vault, f"Add race {n}-{i}", [path])
        except Exception as e:                    # record never raises
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    last = tmp_vault / "last.md"
    last.write_text("last")
    assert vault_history.record(tmp_vault, "Add last", [last])
    for n in range(2):
        for i in range(4):
            assert in_head(tmp_vault, f"race-{n}-{i}.md")


def test_a_git_repository_in_the_vault_is_never_touched(tmp_vault):
    user = Repo.init(str(tmp_vault))
    (tmp_vault / ".git" / "note.txt").write_text("the user's own file")
    save("History One")
    save("History Two")
    assert user.refs.as_dict() == {}              # no commit was made in the user's repository
    assert not in_head(tmp_vault, ".git/note.txt")
    assert not in_head(tmp_vault, ".git/HEAD")


def test_litter_and_the_store_itself_are_never_recorded(tmp_vault):
    for name in (".DS_Store", "draft.swp", "notes~", ".#lock", "scratch.tmp"):
        (tmp_vault / name).write_text("x")
    save("History One")
    for name in (".DS_Store", "draft.swp", "notes~", ".#lock", "scratch.tmp"):
        assert not in_head(tmp_vault, name)
    assert not any(
        key.startswith(b".loci/") for key in vault_history._head(repo(tmp_vault))[1]
    )
    assert vault_history.record(tmp_vault, "swap", [tmp_vault / "draft.swp"]) is None


def test_a_glob_in_a_filename_commits_only_that_file(tmp_vault):
    save("History One")
    (tmp_vault / "Q1 notes.md").write_text("a")
    (tmp_vault / "Q2 notes.md").write_text("b")
    star = tmp_vault / "Q* notes.md"
    star.write_text("c")
    assert vault_history.record(tmp_vault, "Add star", [star])
    assert files_changed(tmp_vault, commits(tmp_vault)[0]) == ["Q* notes.md"]


def test_a_non_latin_title_survives_the_round_trip(tmp_vault):
    saved = save("Привет мир")
    subject = vault_history.history(tmp_vault, saved["path"])[0]["subject"]
    assert subject.startswith("Add document: Привет мир")


def test_writes_do_not_make_the_graph_look_stale(tmp_vault, monkeypatch):
    """The graph rebuilds when a vault subfolder's mtime moves. The store sits two
    levels down, so a commit must not cost a full rebuild per write."""
    builds = []
    real = nx_graph._build
    monkeypatch.setattr(nx_graph, "_build", lambda root: (builds.append(1), real(root))[1])
    for i in range(3):
        save(f"Stale {i}")
        nx_graph.get(tmp_vault)
    assert len(builds) == 1


def test_the_store_is_a_valid_git_repository(tmp_vault):
    if shutil.which("git") is None:
        pytest.skip("git is not installed here; Loci itself does not need it")
    save("History One")
    store = str(vault_history.history_dir(tmp_vault))
    run = lambda *a: subprocess.run(["git", "--git-dir", store, *a], capture_output=True, text=True)
    assert run("fsck").returncode == 0
    assert run("log", "-1", "--format=%an|%s").stdout.startswith("loci|Add document: History One")
    # The timezone sign is easy to get backwards: git must read back our own offset.
    assert run("log", "-1", "--format=%ai").stdout.split()[-1] == time.strftime("%z")


def test_status_says_what_state_history_is_in(tmp_vault, monkeypatch):
    assert vault_history.status(tmp_vault)["state"] == "ready"
    save("History One")
    assert vault_history.status(tmp_vault)["state"] == "on"
    with monkeypatch.context() as broken:
        def full(*a, **k):
            raise OSError("disk full")
        broken.setattr(vault_history, "_commit", full)
        save("History Two")
    failed = vault_history.status(tmp_vault)
    assert failed["state"] == "error" and "disk full" in failed["detail"]
    save("History Three")
    assert vault_history.status(tmp_vault)["state"] == "on"
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "0")
    assert vault_history.status(tmp_vault)["state"] == "off"


def test_ui_server_labels_its_commits_ui_at_startup(tmp_vault):
    from fastapi.testclient import TestClient
    from loci import http_server

    with TestClient(http_server.app):
        assert vault_history._source == "ui"


def test_a_recovered_proxy_node_is_committed(tmp_vault):
    from loci import mcp_server

    path = mcp_server._write_vault_proxy(tmp_vault, api.generate_uid(), {"title": "Recovered One"})
    assert subjects(tmp_vault)[0].startswith("Recover document: Recovered One")
    assert in_head(tmp_vault, str(Path(path).relative_to(tmp_vault)))


def test_health_reports_the_state_of_history(tmp_vault):
    from fastapi.testclient import TestClient
    from loci import http_server

    client = TestClient(http_server.app)
    assert client.get("/api/health").json()["history"]["state"] == "ready"
    save("History One")
    assert client.get("/api/health").json()["history"] == {"state": "on", "detail": ""}


def test_the_startup_notice_says_when_history_is_off(tmp_vault, monkeypatch):
    from loci import mcp_server as server

    def startup_notice():
        server._startup_notice = None
        server._first_ready_work_done = False
        server._run_first_ready_work()
        notice, server._startup_notice = server._startup_notice, None
        server._first_ready_work_done = False
        return notice or ""

    monkeypatch.setenv("LOCI_VAULT_HISTORY", "0")
    assert "Vault history is off" in startup_notice()
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")
    assert "Vault history" not in startup_notice()


def test_two_first_commits_cannot_both_win(tmp_vault):
    (tmp_vault / "a.md").write_text("a")
    repo_ = vault_history._open(tmp_vault, create=True)
    first = vault_history._commit(repo_, None, {}, {}, "one", vault_history.SERVICE_AUTHOR, force=True)[0]
    second = vault_history._commit(repo_, None, {}, {}, "two", vault_history.SERVICE_AUTHOR, force=True)[0]
    assert vault_history._advance(repo_, None, first.id) is True
    assert vault_history._advance(repo_, None, second.id) is False
    assert repo_.refs[vault_history.BRANCH] == first.id


def test_a_second_process_creating_the_store_first_is_not_an_error(tmp_vault, monkeypatch):
    vault_history._open(tmp_vault, create=True)
    real = Repo.init_bare
    monkeypatch.setattr(vault_history, "is_repo", lambda root: False)
    monkeypatch.setattr(Repo, "init_bare", staticmethod(lambda *a, **k: real(*a, **k)))
    assert vault_history._open(tmp_vault, create=True) is not None


def test_a_title_with_a_line_break_cannot_forge_the_trailer(tmp_vault):
    save("History One\n\nSource: forged")
    message = commits(tmp_vault)[0].message.decode()
    assert [l for l in message.splitlines() if l.startswith("Source:")] == ["Source: api"]
    assert message.splitlines()[0].startswith("Add document: History One Source: forged")
    assert message.rstrip().endswith("Source: api")


def test_the_first_patch_keeps_the_text_from_before_the_edit(tmp_vault, monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "0")
    saved = save("History One")
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")
    api.patch(saved["uid"], {"summary": "After the edit"})
    baseline = commits(tmp_vault)[-1]
    assert baseline.message.decode().startswith("Baseline")
    assert "After the edit" not in blob_at(tmp_vault, baseline, rel(tmp_vault, saved))
    assert "After the edit" in blob_at(tmp_vault, commits(tmp_vault)[0], rel(tmp_vault, saved))


def test_the_first_meta_edit_keeps_the_text_from_before_the_edit(tmp_vault, monkeypatch):
    (tmp_vault / "meta").mkdir(exist_ok=True)
    (tmp_vault / "meta" / "tag-dictionary.md").write_text("old tags")
    api.write_meta("tag-dictionary", "new tags")
    baseline = commits(tmp_vault)[-1]
    assert blob_at(tmp_vault, baseline, "meta/tag-dictionary.md") == "old tags"
    assert blob_at(tmp_vault, commits(tmp_vault)[0], "meta/tag-dictionary.md") == "new tags"


def test_ensure_baseline_is_a_no_op_once_history_exists(tmp_vault):
    save("History One")
    before = [c.id for c in commits(tmp_vault)]
    vault_history.ensure_baseline(tmp_vault)
    assert [c.id for c in commits(tmp_vault)] == before


def test_a_file_that_vanishes_during_the_scan_does_not_stop_the_write(tmp_vault, monkeypatch):
    (tmp_vault / "ghost.md").write_text("here")
    real_scan = vault_history.os.scandir

    class Entry:
        def __init__(self, e):
            self._e = e
            self.name, self.path = e.name, e.path
        def is_symlink(self): return self._e.is_symlink()
        def is_dir(self): return self._e.is_dir()
        def is_file(self): return self._e.is_file()
        def stat(self):
            if self.name == "ghost.md":
                raise FileNotFoundError(self.path)
            return self._e.stat()

    class Scan:
        def __init__(self, path): self._s = real_scan(path)
        def __enter__(self): return (Entry(e) for e in self._s.__enter__())
        def __exit__(self, *a): return self._s.__exit__(*a)

    monkeypatch.setattr(vault_history.os, "scandir", Scan)
    save("History One")
    assert subjects(tmp_vault)[0].startswith("Add document: History One")
    assert vault_history.status(tmp_vault)["state"] == "on"


def test_a_failing_history_status_does_not_make_the_vault_look_empty(tmp_vault, monkeypatch):
    from fastapi.testclient import TestClient
    from loci import http_server

    def boom():
        raise RuntimeError("no status")

    monkeypatch.setattr(http_server.vault_api, "history_status", boom)
    body = TestClient(http_server.app).get("/api/health").json()
    assert body["status"] == "ok"
    assert body["history"]["state"] == "unknown"


def test_a_slow_walk_runs_at_most_once_per_interval(tmp_vault, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(vault_history, "_clock", lambda: now[0])
    monkeypatch.setattr(vault_history, "_SCAN_FAST_SECONDS", -1)      # every walk counts as slow
    monkeypatch.setattr(vault_history, "_SLOW_SCAN_INTERVAL_SECONDS", 60.0)
    save("History One")
    (tmp_vault / "by-hand.md").write_text("typed in Obsidian")
    save("History Two")
    assert "Changes made outside Loci" not in subjects(tmp_vault)
    now[0] += 61
    save("History Three")
    assert "Changes made outside Loci" in subjects(tmp_vault)
    assert in_head(tmp_vault, "by-hand.md")


def test_a_fast_walk_runs_on_every_write(tmp_vault, monkeypatch):
    monkeypatch.setattr(vault_history, "_SCAN_FAST_SECONDS", 3600)
    save("History One")
    (tmp_vault / "by-hand.md").write_text("typed in Obsidian")
    save("History Two")
    assert subjects(tmp_vault)[1] == "Changes made outside Loci"


def test_a_skipped_walk_still_commits_the_written_file(tmp_vault, monkeypatch):
    monkeypatch.setattr(vault_history, "_SCAN_FAST_SECONDS", -1)
    save("History One")
    saved = save("History Two")
    assert in_head(tmp_vault, rel(tmp_vault, saved))
    assert subjects(tmp_vault)[0].startswith("Add document: History Two")


def test_a_held_lock_gets_one_retry_not_a_slow_series(tmp_vault, monkeypatch):
    save("History One")
    lock = vault_history.history_dir(tmp_vault) / "refs" / "heads" / "main.lock"
    lock.write_text("")
    sleeps = []
    monkeypatch.setattr(vault_history.time, "sleep", lambda s: sleeps.append(s))
    save("History Two")
    assert len(sleeps) == 1


def test_a_failure_in_another_process_shows_in_status(tmp_vault):
    save("History One")
    assert vault_history.status(tmp_vault)["state"] == "on"
    vault_history._set_error(tmp_vault, "disk is read-only")
    vault_history._last_error.clear()          # the process that failed is not this one
    assert vault_history.status(tmp_vault) == {"state": "error", "detail": "disk is read-only"}


def test_the_next_good_write_clears_a_failure_shown_by_another_process(tmp_vault):
    save("History One")
    vault_history._set_error(tmp_vault, "disk is read-only")
    vault_history._last_error.clear()
    save("History Two")
    assert vault_history.status(tmp_vault)["state"] == "on"
    assert not (tmp_vault / vault_history.STATUS_FILE).exists()


def test_an_edit_that_keeps_the_size_and_restores_the_time_is_still_seen(tmp_vault):
    import os
    save("History One")
    hand = tmp_vault / "by-hand.md"
    hand.write_text("aaaa")
    save("History Two")
    stat = hand.stat()
    hand.write_text("bbbb")                                   # same size
    os.utime(hand, ns=(stat.st_atime_ns, stat.st_mtime_ns))   # the old modification time, as rsync -t does
    save("History Three")
    r = repo(tmp_vault)
    assert blob_at(tmp_vault, r[r.head()], "by-hand.md") == "bbbb"


def test_obsidians_settings_folder_is_never_recorded(tmp_vault):
    (tmp_vault / ".obsidian").mkdir()
    (tmp_vault / ".obsidian" / "workspace.json").write_text("{}")
    save("History One")
    assert not in_head(tmp_vault, ".obsidian/workspace.json")
    (tmp_vault / ".obsidian" / "workspace.json").write_text('{"moved": true}')
    save("History Two")
    assert "Changes made outside Loci" not in subjects(tmp_vault)


def test_a_hand_edit_is_committed_before_a_patch_overwrites_it(tmp_vault):
    saved = save("History One")
    path = Path(saved["path"])
    path.write_text(path.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
    api.patch(saved["uid"], {"summary": "After the patch"})
    newest, before_patch = commits(tmp_vault)[0], commits(tmp_vault)[1]
    assert subjects(tmp_vault)[1] == "Changes made outside Loci"
    assert "hand edit" in blob_at(tmp_vault, before_patch, rel(tmp_vault, saved))
    assert "After the patch" not in blob_at(tmp_vault, before_patch, rel(tmp_vault, saved))
    assert "After the patch" in blob_at(tmp_vault, newest, rel(tmp_vault, saved))


def test_a_hand_edit_to_a_meta_file_is_committed_before_write_meta(tmp_vault):
    save("History One")
    meta = tmp_vault / "meta" / "tag-dictionary.md"
    meta.parent.mkdir(exist_ok=True)
    meta.write_text("first")
    api.write_meta("tag-dictionary", "second")             # records "first" as outside, then "second"
    meta.write_text("typed by hand")
    api.write_meta("tag-dictionary", "third")
    assert blob_at(tmp_vault, commits(tmp_vault)[1], "meta/tag-dictionary.md") == "typed by hand"
    assert blob_at(tmp_vault, commits(tmp_vault)[0], "meta/tag-dictionary.md") == "third"


def test_a_hand_edit_to_a_skill_overlay_is_committed_before_write_skill(tmp_vault):
    save("History One")
    api.write_skill("one", skill="loci-save")
    overlay = tmp_vault / "skills" / "loci-save.md"
    overlay.write_text("typed by hand")
    api.write_skill("two", skill="loci-save")
    assert blob_at(tmp_vault, commits(tmp_vault)[1], "skills/loci-save.md") == "typed by hand"


def test_before_write_adds_no_commit_for_a_file_that_is_up_to_date(tmp_vault):
    saved = save("History One")
    before = len(commits(tmp_vault))
    vault_history.before_write(tmp_vault, [saved["path"]])
    assert len(commits(tmp_vault)) == before


def test_a_failure_cleared_by_another_process_is_not_shown_again(tmp_vault):
    save("History One")
    vault_history._set_error(tmp_vault, "transient")
    assert vault_history.status(tmp_vault)["state"] == "error"
    (tmp_vault / vault_history.STATUS_FILE).unlink()       # the MCP server's next good write does this
    assert vault_history.status(tmp_vault)["state"] == "on"


def test_the_error_is_kept_in_memory_only_when_the_file_cannot_be_written(tmp_vault, monkeypatch):
    save("History One")
    monkeypatch.setattr(Path, "write_text", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
    vault_history._set_error(tmp_vault, "disk is read-only")
    monkeypatch.undo()
    assert vault_history.status(tmp_vault) == {"state": "error", "detail": "disk is read-only"}


def test_a_retry_does_not_walk_the_vault_again(tmp_vault, monkeypatch):
    save("History One")
    walks = []
    real = vault_history._scan
    monkeypatch.setattr(vault_history, "_scan", lambda root: walks.append(1) or real(root))
    real_advance = vault_history._advance
    lost = [0]

    def lose_once(repo_, old, new):
        if lost[0] == 0:
            lost[0] = 1
            return False
        return real_advance(repo_, old, new)

    monkeypatch.setattr(vault_history, "_advance", lose_once)
    monkeypatch.setattr(vault_history.time, "sleep", lambda s: None)
    save("History Two")
    assert len(walks) == 1


def test_the_file_cache_drops_files_that_are_gone(tmp_vault):
    (tmp_vault / "short-lived.md").write_text("x")
    save("History One")
    root = str(tmp_vault.resolve())
    assert (root, b"short-lived.md") in vault_history._stat_cache
    (tmp_vault / "short-lived.md").unlink()
    save("History Two")
    assert (root, b"short-lived.md") not in vault_history._stat_cache


def test_opening_the_store_puts_head_back_on_main(tmp_vault):
    save("History One")
    store = Repo(str(vault_history.history_dir(tmp_vault)))
    store.refs.set_symbolic_ref(b"HEAD", b"refs/heads/master")
    vault_history._open(tmp_vault)
    assert Repo(str(vault_history.history_dir(tmp_vault))).refs.follow(b"HEAD")[0][-1] == vault_history.BRANCH


def test_a_history_that_cannot_be_read_shows_as_an_error(tmp_vault, monkeypatch):
    saved = save("History One")
    monkeypatch.setattr(vault_history, "_head", lambda r: (_ for _ in ()).throw(OSError("corrupt object")))
    assert vault_history.history(tmp_vault, saved["path"]) == []
    assert vault_history.status(tmp_vault) == {"state": "error", "detail": "corrupt object"}


# ---------------------------------------------------------------------------
# Viewing and restoring
# ---------------------------------------------------------------------------

def head_short(vault):
    r = repo(vault)
    return r.head().decode("ascii")[:7]


def test_write_results_carry_the_commit(tmp_vault):
    saved = save("History One")
    assert saved["commit"] == head_short(tmp_vault)
    patched = api.patch(saved["uid"], {"summary": "x"})
    assert patched["commit"] == head_short(tmp_vault)
    assert api.delete(saved["uid"])["commit"]


def test_no_commit_field_when_history_is_off(tmp_vault, monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "0")
    assert "commit" not in save("History One")


def test_history_and_read_an_old_version(tmp_vault):
    saved = save("History One")
    api.patch(saved["uid"], {}, body="replaced body")
    found = api.history(saved["uid"])
    assert [c["subject"].split(" ")[0] for c in found] == ["Update", "Add"]
    old = api.get(saved["uid"], commit=found[1]["commit"])
    assert "hello" in old and "replaced body" not in old
    assert "replaced body" in api.get(saved["uid"])


def test_diff_shows_the_removed_and_added_lines(tmp_vault):
    saved = save("History One")
    patched = api.patch(saved["uid"], {}, body="replaced body")
    text = api.diff(saved["uid"], patched["commit"])
    assert "-hello" in text and "+replaced body" in text


def test_restore_brings_back_a_body_overwritten_by_mistake(tmp_vault):
    saved = save("History One")
    api.patch(saved["uid"], {}, body="oops")
    result = api.restore(saved["uid"], saved["commit"])
    assert result["restored"] and not result["was_deleted"]
    assert "hello" in api.get(saved["uid"])
    assert log(tmp_vault)[0].split("|", 1)[1].startswith("Restore History One")


def test_restore_a_deleted_node_by_uid(tmp_vault):
    saved = save("History One")
    deleted = api.delete(saved["uid"])
    # The file and the graph entry are gone; the uid alone must find it.
    result = api.restore(saved["uid"], f"{deleted['commit']}~1")
    assert result["was_deleted"]
    assert "hello" in api.get(saved["uid"])
    assert api.history(saved["uid"])[0]["subject"].startswith("Restore")


def test_restore_saves_uncommitted_outside_edits_first(tmp_vault):
    saved = save("History One")
    path = Path(saved["path"])
    path.write_text(path.read_text() + "\nedited in a text editor\n")
    result = api.restore(saved["uid"], saved["commit"])
    assert "external_edits_saved_as" in result
    saved_as = next(c for c in commits(tmp_vault) if c.id.decode()[:7] == result["external_edits_saved_as"])
    assert "edited in a text editor" in blob_at(tmp_vault, saved_as, rel(tmp_vault, saved))
    assert "edited in a text editor" not in path.read_text()


def test_undo_last_change_reverts_a_patch(tmp_vault):
    saved = save("History One")
    api.patch(saved["uid"], {}, body="oops")
    out = api.undo_last_change()
    assert out["undone"].startswith("Update History One")
    assert "hello" in api.get(saved["uid"])


def test_undo_last_change_removes_a_new_node_and_a_delete_is_undone(tmp_vault):
    saved = save("History One")
    api.undo_last_change()
    assert not Path(saved["path"]).exists()
    api.undo_last_change()          # undoing the undo brings it back
    assert "hello" in api.get(saved["uid"])


def test_undo_refuses_the_baseline(tmp_vault):
    vault_history.ensure_baseline(tmp_vault)
    with pytest.raises(vault_history.HistoryError, match="baseline"):
        api.undo_last_change()


def test_a_bad_commit_reference_is_refused(tmp_vault):
    saved = save("History One")
    for bad in ["--output=/tmp/x", "main; rm -rf", "", "zzzz"]:
        with pytest.raises(vault_history.HistoryError):
            api.get(saved["uid"], commit=bad)


def test_reading_a_commit_that_deleted_the_file_explains_the_fix(tmp_vault):
    saved = save("History One")
    deleted = api.delete(saved["uid"])
    with pytest.raises(vault_history.HistoryError, match="~1"):
        api.get(saved["uid"], commit=deleted["commit"])


def test_history_with_no_store_says_so(tmp_vault):
    with pytest.raises(vault_history.HistoryError, match="no history"):
        api.history(next(tmp_vault.glob("*.md")).name)


def test_every_history_tool_the_save_skill_names_is_an_mcp_tool():
    import re
    from loci import mcp_server

    skill = Path(mcp_server.__file__).parent / "skills" / "loci-save" / "SKILL.md"
    named = set(re.findall(r"loci__(\w+_vault\w*|undo_\w+)", skill.read_text(encoding="utf-8")))
    registered = set(mcp_server.mcp._tool_manager._tools)
    assert {"history_vault", "diff_vault", "restore_vault", "undo_last_vault_change"} <= named
    assert named <= registered


def test_a_deleted_node_with_an_all_digit_uid_is_still_found(tmp_vault):
    path = tmp_vault / "digits.md"
    path.write_text("---\nuid: '12345678'\ntitle: Digits\ntype: document\n---\nbody\n")
    vault_history.record(tmp_vault, "Add digits", [path])
    path.unlink()
    vault_history.record(tmp_vault, "Delete digits", [path])
    assert vault_history.find_path(tmp_vault, "12345678") == "digits.md"


def test_undo_leaves_the_graph_fresh(tmp_vault):
    save("History One")
    nx_graph.get(tmp_vault)
    api.undo_last_change()
    assert nx_graph._built_at >= nx_graph._vault_dir_mtime(tmp_vault)


def test_a_restore_still_succeeds_when_the_graph_cannot_be_updated(tmp_vault, monkeypatch):
    saved = save("History One")
    api.patch(saved["uid"], {}, body="oops")

    def boom(*a, **k):
        raise RuntimeError("graph is broken")

    monkeypatch.setattr(api.graph, "index_node", boom)
    result = api.restore(saved["uid"], saved["commit"])
    assert result["restored"] and result["commit"]
    assert "hello" in Path(saved["path"]).read_text(encoding="utf-8")
    assert subjects(tmp_vault)[0].startswith("Restore History One")


def test_history_and_restore_work_for_a_deleted_file_named_by_path(tmp_vault):
    saved = save("History One")
    deleted = api.delete(saved["uid"])
    relative = rel(tmp_vault, saved)
    assert api.history(relative)[0]["subject"].startswith("Delete")
    assert "hello" in api.get(relative, commit=f"{deleted['commit']}~1")
    assert api.restore(str(Path(saved["path"])), f"{deleted['commit']}~1")["was_deleted"]
    assert Path(saved["path"]).exists()


def test_a_path_outside_the_vault_is_not_taken_for_a_deleted_node(tmp_vault):
    save("History One")
    assert api.history("../../etc/passwd") == []


def test_a_hash_prefix_that_names_two_commits_is_refused(tmp_vault):
    save("History One")
    repo_ = repo(tmp_vault)
    ids = [c.id.decode() for c in commits(tmp_vault)]
    # Make an ambiguous prefix by planting a second commit that shares the first 4 characters.
    prefix = ids[0][:4]
    real_walker = repo_.get_walker
    fake = type("E", (), {})()
    fake.commit = type("C", (), {"id": (prefix + "f" * 36).encode()})()
    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(Repo, "get_walker", lambda self, **k: list(real_walker(**k)) + [fake])
        with pytest.raises(vault_history.HistoryError, match="more characters"):
            vault_history._resolve(repo_, prefix)
    finally:
        monkey.undo()


def test_a_full_hash_resolves_directly_and_an_unknown_one_is_refused(tmp_vault):
    save("History One")
    repo_ = repo(tmp_vault)
    full = repo_.head().decode()
    assert vault_history._resolve(repo_, full) == repo_.head()
    with pytest.raises(vault_history.HistoryError, match="No commit"):
        vault_history._resolve(repo_, "0" * 40)


def test_head_is_accepted_in_any_case(tmp_vault):
    save("History One")
    repo_ = repo(tmp_vault)
    for ref in ("HEAD", "head", "Head", "head~1"):
        assert vault_history._resolve(repo_, ref)


def test_diff_of_a_commit_with_an_empty_message_does_not_fail(tmp_vault):
    from dulwich.objects import Blob

    save("History One")
    r = repo(tmp_vault)
    head, entries = vault_history._head(r)
    made = vault_history._commit(r, head, entries, {b"empty.md": Blob.from_string(b"x")},
                                 "", vault_history.SERVICE_AUTHOR)
    assert vault_history._advance(r, head, made[0].id)
    assert "+x" in vault_history.diff(tmp_vault, made[0].id.decode()[:7], tmp_vault / "empty.md")


def test_undo_refuses_a_commit_that_holds_edits_made_outside_loci(tmp_vault):
    save("History One")
    hand = tmp_vault / "by-hand.md"
    hand.write_text("typed in Obsidian")
    vault_history.before_write(tmp_vault, [hand])
    assert subjects(tmp_vault)[0] == "Changes made outside Loci"
    with pytest.raises(vault_history.HistoryError, match="outside Loci"):
        api.undo_last_change()
    assert hand.read_text() == "typed in Obsidian"


def test_a_uid_quoted_in_another_notes_body_is_not_taken_for_its_owner(tmp_vault):
    owner = tmp_vault / "owner.md"
    owner.write_text("---\nuid: 12345678\ntitle: Owner\ntype: document\n---\nbody\n")
    vault_history.record(tmp_vault, "Add owner", [owner])
    owner.unlink()
    vault_history.record(tmp_vault, "Delete owner", [owner])
    quoting = tmp_vault / "quoting.md"
    quoting.write_text("---\nuid: abcdef01\ntitle: Quoting\ntype: document\n---\nExample:\nuid: 12345678\n")
    vault_history.record(tmp_vault, "Add quoting", [quoting])
    assert vault_history.find_path(tmp_vault, "12345678") == "owner.md"


def test_an_undo_that_cannot_read_an_old_version_changes_nothing(tmp_vault, monkeypatch):
    one, two = tmp_vault / "f1.md", tmp_vault / "f2.md"
    for f in (one, two):
        f.write_text("v1")
    save("History One")
    vault_history.record(tmp_vault, "Add files", [one, two])
    for f in (one, two):
        f.write_text("v2")
    vault_history.record(tmp_vault, "Change both", [one, two])
    real, calls = vault_history.show, []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) > 1:
            raise vault_history.HistoryError("cannot read")
        return real(*a, **k)

    monkeypatch.setattr(vault_history, "show", flaky)
    with pytest.raises(vault_history.HistoryError):
        api.undo_last_change()
    assert one.read_text() == "v2" and two.read_text() == "v2"


def test_the_history_tools_return_an_error_for_a_disk_failure(tmp_vault, monkeypatch):
    from loci import mcp_server

    def boom(*a, **k):
        raise OSError("disk is full")

    save("History One")
    monkeypatch.setattr(mcp_server.vault, "undo_last_change", boom)
    monkeypatch.setattr(mcp_server.vault, "restore", boom)
    assert mcp_server.undo_last_vault_change() == {"error": "disk is full"}
    assert mcp_server.restore_vault("x", "abcd") == {"error": "disk is full"}


def test_undo_refuses_when_another_write_landed_after_head_was_read(tmp_vault, monkeypatch):
    saved = save("History One")
    api.patch(saved["uid"], {}, body="oops")
    real = vault_history.head_changes

    def head_then_write(root):
        out = real(root)
        api.patch(saved["uid"], {}, body="newer")   # a second process commits here
        return out

    monkeypatch.setattr(vault_history, "head_changes", head_then_write)
    with pytest.raises(vault_history.HistoryError, match="changed while"):
        api.undo_last_change()
    assert "newer" in api.get(saved["uid"])


def test_undo_of_a_meta_change_resets_the_registries(tmp_vault):
    from loci.tools.type_registry import REFERENCES_DIR, get_registry, reset_registry
    (tmp_vault / "meta").mkdir()
    for name in ("ontology.yaml", "ontology-user.yaml"):
        shutil.copy(REFERENCES_DIR / name, tmp_vault / "meta" / name)
    reset_registry()
    api.define_type("zzwidget", "document", "A test type")
    assert "zzwidget" in get_registry(tmp_vault).type_names()
    api.undo_last_change()
    assert "zzwidget" not in get_registry(tmp_vault).type_names()
    reset_registry()


def test_diff_names_a_change_to_the_final_newline(tmp_vault):
    saved = save("History One")
    p = Path(saved["path"])
    text = p.read_text(encoding="utf-8")
    assert not text.endswith("\n")
    p.write_text(text + "\n", encoding="utf-8")
    commit = vault_history.record(tmp_vault, "trim newline", [p])
    assert commit
    out = vault_history.diff(tmp_vault, commit, p)
    assert "final newline" in out


def test_restore_refuses_a_version_without_a_uid(tmp_vault):
    saved = save("History One")
    p = Path(saved["path"])
    p.write_text("no frontmatter here\n", encoding="utf-8")
    api._record("break it", p)
    broken = vault_history.head_short(tmp_vault)
    with pytest.raises(ValueError, match="no uid"):
        api.restore(saved["path"], broken)


def test_find_path_caches_a_miss_until_head_moves(tmp_vault, monkeypatch):
    saved = save("History One")
    assert vault_history.find_path(tmp_vault, "deadbeef") is None
    calls = []
    real = vault_history._scan_for_uid
    monkeypatch.setattr(vault_history, "_scan_for_uid", lambda *a: calls.append(1) or real(*a))
    vault_history.find_path(tmp_vault, "deadbeef")
    assert not calls
    api.patch(saved["uid"], {}, body="x")
    vault_history.find_path(tmp_vault, "deadbeef")
    assert calls


def test_restore_warns_when_the_type_is_unknown_now(tmp_vault):
    saved = save("History One")
    p = Path(saved["path"])
    p.write_text(p.read_text(encoding="utf-8").replace("type: document", "type: zzgone"), encoding="utf-8")
    bad = vault_history.record(tmp_vault, "retype", [p])
    result = api.restore(saved["path"], bad)
    assert "zzgone" in result["warning"]
    assert "warning" not in api.restore(saved["path"], saved["commit"])
