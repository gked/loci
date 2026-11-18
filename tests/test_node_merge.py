"""
Conflicted copies: the "(conflicted copy …)" file a sync tool leaves when the same
node was edited on two computers. Loci merges it into the node, using the version
both edits started from, which the vault history holds.
"""

import pytest

from loci import api, http_server
from loci.tools import node_merge, nx_graph, vault_history
from loci.tools.frontmatter import load_frontmatter
from loci.tools.node_merge import Clash, MergeError, merge3
from loci.tools.vault_linter import lint_vault
from loci.tools.write_file import find_uid

from test_http_server import TOKEN, auth, client  # noqa: F401  (fixtures)


@pytest.fixture(autouse=True)
def history_on(monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")
    vault_history.set_source("api")
    vault_history._stat_cache.clear()
    vault_history._last_error.clear()
    vault_history._last_walk.clear()
    yield
    vault_history.set_source("api")


@pytest.fixture
def as_computer(tmp_path, monkeypatch):
    def switch(name):
        monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / f"cfg-{name}" / "config.yml"))
        return vault_history.computer_id()
    return switch


BASE = "one\ntwo\nthree\nfour\nfive\n"
COPY_SUFFIX = " (conflicted copy 2026-11-14 081923).md"


def _resolve(vault, copy_name, choices=None, token=None):
    """node_merge.resolve with the token `describe` would hand out, like a caller that listed first."""
    if token is None:
        token = node_merge.describe(vault, copy_name)["token"]
    return node_merge.resolve(vault, copy_name, choices, token=token)


def diverge(vault, as_computer, base=BASE, a=None, b=None):
    """Computer A saves a node. Computer B edits it. A, whose disk still holds the
    version it saved, edits it too. The sync tool keeps A's file and saves B's
    as a conflicted copy. Returns (node path, copy path)."""
    as_computer("a")
    saved = api.save(type="document", title="Shared", body=base,
                     extra_fields={"status": "draft", "subtype": "note"})
    node = vault / saved["path"].rsplit("/", 1)[-1]
    first = node.read_text()
    as_computer("b")
    api.patch(saved["uid"], {}, body=b if b is not None else BASE)
    theirs = node.read_text()
    node.write_text(first)                      # A's disk: B's edit has not arrived
    as_computer("a")
    api.patch(saved["uid"], {}, body=a if a is not None else BASE)
    copy = node.with_name(node.stem + COPY_SUFFIX)
    copy.write_text(theirs)
    return node, copy


# ---------------------------------------------------------------------------
# merge3
# ---------------------------------------------------------------------------

def test_edits_to_different_lines_merge():
    out = merge3(BASE, "one\nTWO\nthree\nfour\nfive\n", "one\ntwo\nthree\nfour\nFIVE\n")
    assert out == ["one\nTWO\nthree\nfour\nFIVE\n"]


def test_edits_to_the_same_line_clash():
    out = merge3(BASE, "one\nA\nthree\nfour\nfive\n", "one\nB\nthree\nfour\nfive\n")
    assert out[0] == "one\n"
    assert out[1] == Clash(base=["two\n"], a=["A\n"], b=["B\n"])
    assert out[2] == "three\nfour\nfive\n"


def test_the_same_edit_on_both_sides_is_not_a_clash():
    same = "one\ntwo\nthree\nfour\nFIVE\n"
    assert merge3(BASE, same, same) == [same]


def test_one_side_adding_lines_and_the_other_changing_one_merge():
    out = merge3(BASE, BASE + "six\n", "ONE\ntwo\nthree\nfour\nfive\n")
    assert out == ["ONE\ntwo\nthree\nfour\nfive\nsix\n"]


def test_a_line_one_side_deleted_and_the_other_changed_clashes():
    out = merge3(BASE, "one\nthree\nfour\nfive\n", "one\nTWO\nthree\nfour\nfive\n")
    assert [s for s in out if isinstance(s, Clash)] == [Clash(["two\n"], [], ["TWO\n"])]


def test_both_sides_adding_different_text_at_one_place_clash():
    out = merge3("", "x\n", "y\n")
    assert out == [Clash([], ["x\n"], ["y\n"])]


def test_line_endings_are_kept():
    base = "one\r\ntwo\r\nthree\r\n"
    out = merge3(base, "ONE\r\ntwo\r\nthree\r\n", "one\r\ntwo\r\nTHREE\r\n")
    assert out == ["ONE\r\ntwo\r\nTHREE\r\n"]


def test_a_missing_final_newline_is_not_an_edit():
    # The missing newline is no clash, and the result ends as the kept file (the second argument) does.
    assert merge3("a\nb\n", "a\nb", "A\nb\n") == ["A\nb"]
    assert merge3("a\nb\n", "a\nb\n", "A\nb") == ["A\nb\n"]


# ---------------------------------------------------------------------------
# Finding copies
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name, original", [
    ("note (conflicted copy 2026-11-14 081923).md", "note.md"),
    ("note (Max's conflicted copy 2026-11-14).md", "note.md"),
    ("two words (Conflicted Copy 1).md", "two words.md"),
])
def test_copy_names_are_recognised(name, original):
    assert node_merge.is_conflicted_copy(name)
    assert node_merge.original_name(name) == original


@pytest.mark.parametrize("name", ["note.md", "conflicted copy.md", "note (draft).md", "note (conflicted copy).txt"])
def test_other_names_are_not_copies(name):
    assert not node_merge.is_conflicted_copy(name)


def test_conflicted_copies_lists_only_the_copies(tmp_path):
    (tmp_path / "a.md").write_text("x")
    (tmp_path / ("a" + COPY_SUFFIX)).write_text("x")
    assert [p.name for p in node_merge.conflicted_copies(tmp_path)] == ["a" + COPY_SUFFIX]


def test_a_copy_is_not_a_node(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE + "mine\n", b=BASE + "theirs\n")
    nx_graph._graph = None
    graph = nx_graph.get(tmp_vault)
    paths = [d.get("path") for _, d in graph.nodes(data=True)]
    assert str(node) in paths
    assert str(copy) not in paths
    fm_uid = str(load_frontmatter(node.read_text())[0]["uid"])    # not split by hand: an all-digit uid is quoted
    assert find_uid(tmp_vault, fm_uid) == node


def test_a_copy_is_not_a_node_when_the_uid_is_all_digits(tmp_vault, as_computer, monkeypatch):
    """YAML quotes an all-digit uid (`uid: '12345678'`); the lookup must still find the node."""
    monkeypatch.setattr("loci.tools.write_file.generate_uid", lambda: "12345678")
    node, copy = diverge(tmp_vault, as_computer, a=BASE + "mine\n", b=BASE + "theirs\n")
    assert "uid: '12345678'" in node.read_text()
    nx_graph._graph = None
    assert find_uid(tmp_vault, "12345678") == node
    assert str(copy) not in [d.get("path") for _, d in nx_graph.get(tmp_vault).nodes(data=True)]


def test_lint_reports_the_copy_once_and_not_as_a_duplicate(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE + "mine\n", b=BASE + "theirs\n")
    result = lint_vault(tmp_vault)
    codes = {(i["path"], i["code"]) for i in result["errors"]}
    assert (copy.name, "conflicted-copy") in codes
    assert not any(code == "duplicate-uid" for _, code in codes)
    assert result["stats"]["conflicted_copies"] == 1


# ---------------------------------------------------------------------------
# Resolving
# ---------------------------------------------------------------------------

def test_the_merge_base_is_the_version_both_edits_started_from(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a="ONE\ntwo\nthree\nfour\nfive\n", b=BASE.replace("five", "FIVE"))
    base = vault_history.merge_base_text(tmp_vault, node)
    assert base is not None and BASE in base
    assert "ONE" not in base and "FIVE" not in base


def test_edits_to_different_lines_merge_with_no_question(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a="ONE\ntwo\nthree\nfour\nfive\n", b=BASE.replace("five", "FIVE"))

    described = node_merge.describe(tmp_vault, copy.name)
    assert described["kind"] == "merged"

    out = _resolve(tmp_vault, copy.name)

    assert out["kind"] == "merged"
    text = node.read_text()
    assert "ONE\ntwo\nthree\nfour\nFIVE\n" in text
    assert not copy.exists()


def test_the_merge_is_one_commit_and_the_copy_is_recorded_before_it_goes(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a="ONE\ntwo\nthree\nfour\nfive\n", b=BASE.replace("five", "FIVE"))
    theirs = copy.read_text()

    _resolve(tmp_vault, copy.name)

    # Commits made in one second have no fixed order among themselves.
    listed = vault_history.history(tmp_vault, node)
    assert "Merged conflicted copy of " + node.name in [c["subject"] for c in listed]
    # The copy's own text can be read back from the history.
    found = [c for c in vault_history.history(tmp_vault, copy)]
    assert found, "the copy was never recorded"
    assert vault_history.show(tmp_vault, found[-1]["commit"], copy) == theirs


def test_the_other_computers_line_is_joined_by_the_merge(tmp_vault, as_computer):
    from loci.tools.vault_history import _open, _tips, _head, _descends
    node, copy = diverge(tmp_vault, as_computer, a="ONE\ntwo\nthree\nfour\nfive\n", b=BASE.replace("five", "FIVE"))
    b_tip = [sha for name, sha in _tips(_open(tmp_vault)).items() if name != vault_history.computer_id().encode()][0]

    _resolve(tmp_vault, copy.name)

    repo = _open(tmp_vault)
    head, _ = _head(repo)
    assert _descends(repo, b_tip, head)


def test_edits_to_the_same_line_wait_for_a_choice(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("two", "mine"), b=BASE.replace("two", "theirs"))
    before = node.read_text()

    described = node_merge.describe(tmp_vault, copy.name)
    assert described["kind"] == "conflict"
    assert [(c["a"], c["b"]) for c in described["clashes"]] == [("mine\n", "theirs\n")]

    with pytest.raises(MergeError, match="1 clashing"):
        _resolve(tmp_vault, copy.name)
    with pytest.raises(MergeError):
        _resolve(tmp_vault, copy.name, ["c"])
    assert node.read_text() == before and copy.exists()      # nothing changed


@pytest.mark.parametrize("pick, kept, dropped", [("a", "mine", "theirs"), ("b", "theirs", "mine")])
def test_the_choice_decides_the_clashing_lines_only(tmp_vault, as_computer, pick, kept, dropped):
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("two", "mine").replace("five", "FIVE"),
                         b=BASE.replace("two", "theirs"))

    _resolve(tmp_vault, copy.name, [pick])

    text = node.read_text()
    assert f"one\n{kept}\nthree\nfour\nFIVE\n" in text
    assert dropped not in text
    assert not copy.exists()


def test_updated_at_alone_is_never_a_clash(tmp_vault, as_computer):
    """Both computers stamp updated_at on every edit, so it differs on every merge.
    The merged node takes the later stamp."""
    node, copy = diverge(tmp_vault, as_computer, a="ONE\ntwo\nthree\nfour\nfive\n", b=BASE.replace("five", "FIVE"))
    lines = copy.read_text().splitlines(keepends=True)
    copy.write_text("".join("updated_at: '2099-01-01T00:00:00Z'\n" if l.startswith("updated_at:") else l for l in lines))

    assert node_merge.describe(tmp_vault, copy.name)["kind"] == "merged"
    _resolve(tmp_vault, copy.name)

    assert "updated_at: '2099-01-01T00:00:00Z'" in node.read_text()


def test_identical_files_merge_to_that_file(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer)
    copy.write_text(node.read_text())
    assert node_merge.describe(tmp_vault, copy.name)["kind"] == "merged"
    _resolve(tmp_vault, copy.name)
    assert not copy.exists()


def test_an_edit_beats_a_delete(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, b=BASE + "edited\n")
    node.unlink()                                            # the other computer deleted it

    assert node_merge.describe(tmp_vault, copy.name)["kind"] == "restore"
    _resolve(tmp_vault, copy.name)

    assert node.is_file() and "edited" in node.read_text()
    assert not copy.exists()
    subjects = [c["subject"] for c in vault_history.history(tmp_vault, node)]
    assert any(x.startswith("Edit on the other computer overrode a delete") for x in subjects)


def test_two_different_nodes_with_one_file_name_are_both_kept(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer)
    other_uid = "deadbeef"
    old_uid = [l for l in copy.read_text().splitlines() if l.startswith("uid:")][0]
    copy.write_text(copy.read_text().replace(old_uid, f"uid: {other_uid}"))

    described = node_merge.describe(tmp_vault, copy.name)
    assert described["kind"] == "keep-both"
    _resolve(tmp_vault, copy.name)

    kept = tmp_vault / described["new_name"]
    assert kept.is_file() and f"uid: {other_uid}" in kept.read_text()
    assert not copy.exists() and node.is_file()


def test_a_name_that_is_not_a_copy_is_refused(tmp_vault):
    (tmp_vault / "plain.md").write_text("x")
    for bad in ("plain.md", "../x (conflicted copy 1).md", "missing (conflicted copy 1).md"):
        with pytest.raises(MergeError):
            node_merge.describe(tmp_vault, bad)
    with pytest.raises(MergeError):
        _resolve(tmp_vault, "plain.md")


def test_without_history_both_files_are_clashes_for_the_user(tmp_vault, monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "0")
    (tmp_vault / "n.md").write_text("---\nuid: 11111111\n---\nmine\n")
    (tmp_vault / ("n" + COPY_SUFFIX)).write_text("---\nuid: 11111111\n---\ntheirs\n")
    described = node_merge.describe(tmp_vault, "n" + COPY_SUFFIX)
    assert described["kind"] == "conflict"


def test_a_merge_gets_no_final_newline_the_kept_file_lacks():
    merged = "".join(merge3("a\nb\nc", "a\nB\nc", "a\nb\nc"))
    assert merged == "a\nB\nc"
    # With a final newline in the kept file, the result keeps it.
    assert "".join(merge3("a\nb\nc\n", "a\nB\nc\n", "a\nb\nc\n")) == "a\nB\nc\n"


def test_list_items_does_not_list_a_conflicted_copy(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("two", "mine"), b=BASE.replace("two", "theirs"))
    listed = [name for names in api.list_items().values() for name in names]
    assert node.name in listed
    assert copy.name not in listed


def test_choices_for_clashes_that_changed_are_refused(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("two", "mine"), b=BASE.replace("two", "theirs"))
    token = node_merge.describe(tmp_vault, copy.name)["token"]
    # New edits arrive after the page loaded. There is still one clash, but a different one.
    copy.write_text(copy.read_text().replace("theirs", "other"))
    before = node.read_text()

    with pytest.raises(MergeError, match="changed since"):
        _resolve(tmp_vault, copy.name, ["b"], token=token)

    assert node.read_text() == before and copy.exists()


def test_choices_with_the_current_token_are_applied(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("two", "mine"), b=BASE.replace("two", "theirs"))
    token = node_merge.describe(tmp_vault, copy.name)["token"]
    _resolve(tmp_vault, copy.name, ["b"], token=token)
    assert "theirs" in node.read_text() and not copy.exists()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class TestConflictEndpoints:
    HEADERS = {"Origin": "http://localhost:5173", "X-Loci-Token": TOKEN}

    @pytest.fixture(autouse=True)
    def vault(self, monkeypatch, tmp_vault):
        monkeypatch.setattr(http_server, "_VAULT_ROOT", tmp_vault)

    def test_a_vault_without_copies_has_none(self, client):
        assert client.get("/api/conflicts").json() == []
        assert client.get("/api/health").json()["conflicts"] == 0

    def test_health_counts_the_copies(self, client, tmp_vault, as_computer):
        diverge(tmp_vault, as_computer, a=BASE.replace("two", "mine"), b=BASE.replace("two", "theirs"))
        assert client.get("/api/health").json()["conflicts"] == 1

    def test_list_and_resolve(self, client, tmp_vault, as_computer):
        node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("two", "mine"), b=BASE.replace("two", "theirs"))

        listed = client.get("/api/conflicts").json()
        assert listed[0]["copy"] == copy.name and listed[0]["kind"] == "conflict"

        response = client.post("/api/conflicts/resolve", headers=self.HEADERS,
                               json={"file": copy.name, "choices": ["b"]})
        assert response.status_code == 409 and copy.exists()        # no token: not applied blind
        response = client.post("/api/conflicts/resolve", headers=self.HEADERS,
                               json={"file": copy.name, "choices": ["b"], "token": listed[0]["token"]})
        assert response.status_code == 200
        assert "theirs" in node.read_text() and not copy.exists()
        assert client.get("/api/conflicts").json() == []

    def test_a_stale_token_is_a_409_and_changes_nothing(self, client, tmp_vault, as_computer):
        node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("two", "mine"), b=BASE.replace("two", "theirs"))
        token = client.get("/api/conflicts").json()[0]["token"]
        copy.write_text(copy.read_text().replace("theirs", "other"))
        response = client.post("/api/conflicts/resolve", headers=self.HEADERS,
                               json={"file": copy.name, "choices": ["b"], "token": token})
        assert response.status_code == 409
        assert copy.exists()

    def test_a_failed_count_is_logged(self, client, monkeypatch, caplog):
        def boom():
            raise OSError("vault unreadable")
        monkeypatch.setattr(http_server.vault_api, "conflict_count", boom)
        with caplog.at_level("WARNING"):
            assert http_server._conflict_count() == 0
        assert "counting conflicted copies failed" in caplog.text

    def test_resolve_needs_the_token(self, client, tmp_vault, as_computer):
        node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("two", "mine"), b=BASE.replace("two", "theirs"))
        response = client.post("/api/conflicts/resolve", json={"file": copy.name, "choices": ["a"]})
        assert response.status_code in (401, 403)
        assert copy.exists()

    def test_a_missing_choice_is_a_409_and_changes_nothing(self, client, tmp_vault, as_computer):
        node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("two", "mine"), b=BASE.replace("two", "theirs"))
        response = client.post("/api/conflicts/resolve", headers=self.HEADERS, json={"file": copy.name})
        assert response.status_code == 409
        assert copy.exists()


def test_resolve_needs_a_token_for_every_kind(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a="ONE\ntwo\nthree\nfour\nfive\n", b="one\ntwo\nthree\nfour\nFIVE\n")
    with pytest.raises(node_merge.MergeError, match="token is required"):
        node_merge.resolve(tmp_vault, copy.name)
    assert copy.exists()
    token = node_merge.describe(tmp_vault, copy.name)["token"]
    copy.write_text(copy.read_text().replace("FIVE", "SIX"))              # the files moved on
    with pytest.raises(node_merge.MergeError, match="changed since"):
        node_merge.resolve(tmp_vault, copy.name, token=token)
    assert copy.exists()


def test_choices_for_a_restore_are_an_error_not_ignored(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE, b=BASE.replace("three", "BBB"))
    node.unlink()                                                          # deleted on the other computer
    assert node_merge.describe(tmp_vault, copy.name)["kind"] == "restore"
    with pytest.raises(node_merge.MergeError, match="takes no choices"):
        _resolve(tmp_vault, copy.name, ["a"])
    assert copy.exists() and not node.exists()
