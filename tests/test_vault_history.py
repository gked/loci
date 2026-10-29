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
    assert vault_history.record(tmp_vault, "No change", [saved["path"]]) is False
    assert len(log(tmp_vault)) == before


def test_meta_and_overlay_writes_are_committed(tmp_vault):
    api.write_meta("tag-dictionary", "# tags\n")
    assert subjects(tmp_vault)[0] == "Update meta: tag-dictionary"


def test_assets_outside_the_vault_are_never_committed(tmp_vault):
    outside = tmp_vault.parent / "assets" / "x.bin"
    outside.parent.mkdir()
    outside.write_bytes(b"\0")
    assert vault_history.record(tmp_vault, "asset", [outside]) is False


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
    assert vault_history.record(tmp_vault, "swap", [tmp_vault / "draft.swp"]) is False


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
