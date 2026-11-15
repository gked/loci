"""
Files dropped into the vault by hand: no frontmatter, a copied uid, a binary
file. History records all of them. The lint check names each problem, and a
shared uid never lets a copy hide the older node.
"""

from pathlib import Path

import pytest

from loci import api
from loci.tools import nx_graph, vault_history
from loci.tools.vault_linter import lint_vault
from loci.tools.write_file import find_uid


@pytest.fixture(autouse=True)
def history_on(monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")
    vault_history.set_source("api")
    vault_history._stat_cache.clear()
    vault_history._last_error.clear()
    vault_history._last_walk.clear()
    yield
    vault_history.set_source("api")


def codes(result):
    return {(i["path"], i["code"]) for i in result["errors"] + result["warnings"]}


def test_a_file_without_frontmatter_is_flagged_with_the_way_out(tmp_vault):
    (tmp_vault / "dropped.md").write_text("# just text\n")
    result = lint_vault(tmp_vault)
    issue = next(i for i in result["errors"] if i["path"] == "dropped.md")
    assert issue["code"] == "no-frontmatter"
    assert "does not guess" in issue["message"]
    assert (tmp_vault / "dropped.md").read_text() == "# just text\n"      # never changed by the check


def test_a_binary_file_is_flagged_and_does_not_break_the_lint(tmp_vault):
    (tmp_vault / "scan.pdf").write_bytes(b"%PDF-1.4\x00\xff\xfe")
    (tmp_vault / "binary.md").write_bytes(b"---\nuid: 12345678\n---\n\xff\xfe\x00")
    result = lint_vault(tmp_vault)
    found = codes(result)
    assert ("scan.pdf", "non-note-file") in found
    assert ("binary.md", "unreadable") in found


def test_hidden_files_and_editor_leftovers_are_not_flagged(tmp_vault):
    for name in (".DS_Store", "note.md~", "x.swp", "x.tmp", ".gitignore"):
        (tmp_vault / name).write_text("x")
    assert not [i for i in lint_vault(tmp_vault)["warnings"] if i["code"] == "non-note-file"]


def test_history_records_every_kind_of_dropped_file(tmp_vault):
    api.save(type="document", title="First", body="hello", extra_fields={"status": "draft", "subtype": "note"})
    (tmp_vault / "dropped.md").write_text("no header")
    (tmp_vault / "binary.md").write_bytes(b"\xff\xfe\x00")
    (tmp_vault / "scan.pdf").write_bytes(b"%PDF\x00")
    assert vault_history.snapshot_outside(tmp_vault)
    for name in ("dropped.md", "binary.md", "scan.pdf"):
        assert vault_history.history(tmp_vault, name), name


@pytest.fixture
def twin(tmp_vault):
    """An older node, and a note dropped in later with the same uid."""
    original = next(p for p in sorted(tmp_vault.glob("*.md")) if "uid:" in p.read_text())
    text = original.read_text()
    uid = next(l for l in text.splitlines() if l.startswith("uid:")).split(": ")[1].strip()
    copy = tmp_vault / "zzz-copy.md"
    created = [l for l in text.splitlines() if l.startswith("created_at:")]
    stamped = text.replace(created[0], "created_at: '2099-01-01T00:00:00Z'") if created else text
    copy.write_text(stamped)
    return original, copy, uid


def test_the_older_node_keeps_the_uid_in_the_lookup(tmp_vault, twin):
    original, copy, uid = twin
    assert find_uid(tmp_vault, uid) == original


def test_the_older_node_keeps_the_uid_in_the_graph(tmp_vault, twin):
    original, copy, uid = twin
    nx_graph._graph = None
    assert nx_graph.get(tmp_vault).nodes[uid]["path"] == str(original)


def test_lint_flags_the_copy_and_says_which_node_keeps_the_uid(tmp_vault, twin):
    original, copy, uid = twin
    result = lint_vault(tmp_vault)
    issues = [i for i in result["errors"] if i["code"] == "duplicate-uid" and i["path"] == copy.name]
    assert issues and "older node keeps the uid" in issues[0]["message"]


def test_the_fix_gives_the_newer_file_a_new_uid_and_touches_nothing_else(tmp_vault, twin):
    original, copy, uid = twin
    body_before = copy.read_text().split("---", 2)[2]
    original_before = original.read_text()

    out = api.fix_duplicate_uid(str(copy))

    assert out["old_uid"] == uid and out["new_uid"] != uid
    assert f"uid: {out['new_uid']}" in copy.read_text()
    assert copy.read_text().split("---", 2)[2] == body_before
    assert original.read_text() == original_before
    assert not [i for i in lint_vault(tmp_vault)["errors"] if i["code"] == "duplicate-uid"]


def test_the_fix_refuses_the_older_node_and_a_unique_uid(tmp_vault, twin):
    original, copy, uid = twin
    with pytest.raises(ValueError, match="not the newer holder"):
        api.fix_duplicate_uid(str(original))
    api.fix_duplicate_uid(str(copy))
    with pytest.raises(ValueError, match="not the newer holder"):
        api.fix_duplicate_uid(str(copy))


def test_a_copy_with_an_identical_header_loses_in_the_graph_and_the_lookup_alike(tmp_vault, twin):
    original, copy, uid = twin
    copy.write_text(original.read_text())           # same uid, same created_at
    smaller = min(original, copy, key=lambda p: p.name)
    nx_graph._graph = None
    assert find_uid(tmp_vault, uid) == smaller
    assert nx_graph.get(tmp_vault).nodes[uid]["path"] == str(smaller)


def test_a_discarded_copy_leaves_no_relations_in_the_graph(tmp_vault, twin, monkeypatch):
    original, copy, uid = twin
    real = Path.rglob       # read the copy first, so the older file replaces it
    monkeypatch.setattr(Path, "rglob", lambda self, pat: iter(sorted(real(self, pat), key=lambda p: p.name, reverse=True)))
    text = copy.read_text()
    assert "relations: []" in text
    copy.write_text(text.replace("relations: []", "relations:\n- type: relates-to\n  uid: deadbeef", 1))
    nx_graph._graph = None
    assert not nx_graph.get(tmp_vault).has_edge(uid, "deadbeef")

