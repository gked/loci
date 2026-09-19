"""
tests/test_subtypes.py
ontology_version 2: `subtype` on task, document, and article.

Three things have to hold together. The registry must declare the enums, the
writer must refuse a task or document without one, and the graph must let a
caller ask for "my essays" by subtype rather than by a tag that may or may
not have been applied. The migration script that brings an existing vault
across is tested here too, against the fixture vault, since that is the only
vault the suite is allowed to reshape.
"""
import sys
from pathlib import Path

import pytest
import yaml

from loci import api
from loci.tools import nx_graph as graph
from loci.tools.frontmatter import split_frontmatter
from loci.tools.type_registry import get_registry
from loci.tools.vault_linter import lint_vault
from loci.tools.write_file import validate_required_fields

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import migrate_subtypes  # noqa: E402  (must follow sys.path insert)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_task_and_document_require_a_subtype_from_a_closed_list():
    registry = get_registry(None)
    task = registry.get("task")
    document = registry.get("document")

    assert "subtype" in task.required_names()
    assert "subtype" in document.required_names()
    assert task.enum_constraints()["subtype"] == {"bug", "feature", "question", "chore"}
    assert document.enum_constraints()["subtype"] == {
        "meeting-notes", "report", "spec", "plan", "transcript", "essay", "journal", "note",
    }


def test_article_medium_is_called_subtype_not_format():
    article = get_registry(None).get("article")
    names = {f.name for f in article.required_fields + article.optional_fields}

    assert "subtype" in article.required_names()
    assert "format" not in names
    assert "book" in article.enum_constraints()["subtype"]


# ---------------------------------------------------------------------------
# Write validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("node_type, fields", [
    ("task", {"status": "todo"}),
    ("document", {"status": "draft"}),
    ("article", {"source_url": "https://example.com"}),
])
def test_write_is_blocked_without_a_subtype(node_type, fields):
    type_def = get_registry(None).get(node_type)
    errors = validate_required_fields(type_def, fields)
    assert any("subtype" in e for e in errors)


def test_write_is_blocked_by_a_subtype_outside_the_list():
    type_def = get_registry(None).get("task")
    errors = validate_required_fields(type_def, {"status": "todo", "subtype": "epic"})
    assert any("subtype" in e for e in errors)


def test_save_document_with_subtype_lands_in_the_graph(tmp_vault):
    graph.get(tmp_vault)  # build first, so the save's index_node is what puts the subtype there
    result = api.save(
        type="document", title="On Attention", body="…",
        extra_fields={"status": "draft", "subtype": "essay"},
    )
    assert "errors" not in result

    essays = graph.find(node_type="document", subtype="essay")
    assert [n["uid"] for n in essays] == [result["uid"]]
    assert essays[0]["subtype"] == "essay"


def test_save_asset_document_defaults_to_note_in_file_and_graph_alike(tmp_vault):
    graph.get(tmp_vault)
    result = api.save_asset(
        content=b"%PDF-1", format="pdf", mime_type="application/pdf",
        title="Quarterly Numbers", node_type="document",
    )

    fm = yaml.safe_load(split_frontmatter(Path(result["vault_path"]).read_text(encoding="utf-8"))[0])
    assert fm["subtype"] == "note"
    # The graph was indexed by the save, not rebuilt — it must say the same thing.
    assert [n["uid"] for n in graph.find(node_type="document", subtype="note") if n["uid"] == result["uid"]]


def test_save_asset_intent_carries_the_document_subtype_for_recovery(tmp_vault, monkeypatch):
    """A save interrupted after the asset rename is rebuilt from the intent file;
    the intent has to say `transcript`, or recovery rewrites it as a note."""
    from loci.tools import asset_registry as ar
    from loci import mcp_server

    captured = {}
    real_write_intent = ar.write_intent

    def spy(*args, **kwargs):
        captured["vault_node"] = args[-1]
        return real_write_intent(*args, **kwargs)

    monkeypatch.setattr(ar, "write_intent", spy)
    api.save_asset(
        content=b"%PDF-1", format="pdf", mime_type="application/pdf",
        title="Lesson Three", node_type="document", subtype="transcript",
    )
    assert captured["vault_node"]["subtype"] == "transcript"

    # Replay recovery from that intent and read back what it wrote.
    uid = api.generate_uid()
    path = mcp_server._write_vault_proxy(tmp_vault, uid, captured["vault_node"])
    fm = yaml.safe_load(split_frontmatter(Path(path).read_text(encoding="utf-8"))[0])
    assert fm["subtype"] == "transcript"

    # An intent from before type/subtype were recorded still recovers, as a document note.
    legacy = {k: v for k, v in captured["vault_node"].items() if k not in ("type", "subtype", "extra_fields")}
    legacy["title"] = "Legacy Intent"
    path = mcp_server._write_vault_proxy(tmp_vault, api.generate_uid(), legacy)
    fm = yaml.safe_load(split_frontmatter(Path(path).read_text(encoding="utf-8"))[0])
    assert (fm["type"], fm["subtype"]) == ("document", "note")


def test_recovery_of_an_asset_save_writes_an_asset_node_not_a_document(tmp_vault, monkeypatch):
    """The intent used to say nothing about node_type, so an interrupted ebook
    save came back as a document. Now it carries the node exactly as saved."""
    from loci.tools import asset_registry as ar
    from loci import mcp_server

    captured = {}
    real_write_intent = ar.write_intent

    def spy(*args, **kwargs):
        captured["vault_node"] = args[-1]
        return real_write_intent(*args, **kwargs)

    monkeypatch.setattr(ar, "write_intent", spy)
    live = api.save_asset(
        content=b"%PDF-1", format="epub", mime_type="application/epub+zip",
        title="Some Novel", node_type="asset", subtype="book",
        author="A. Writer", published_at="2001", language="en",
    )
    live_fm = yaml.safe_load(split_frontmatter(Path(live["vault_path"]).read_text(encoding="utf-8"))[0])

    node = dict(captured["vault_node"], title="Some Novel (recovered)")
    path = mcp_server._write_vault_proxy(tmp_vault, api.generate_uid(), node)
    recovered_fm = yaml.safe_load(split_frontmatter(Path(path).read_text(encoding="utf-8"))[0])

    assert recovered_fm["type"] == "asset"
    for key in ("subtype", "storage", "author", "published_at", "language", "status", "has_asset"):
        assert recovered_fm[key] == live_fm[key], key


def test_patch_that_finishes_a_note_into_an_essay_moves_it_in_the_graph(tmp_vault):
    node = api.save(
        type="document", title="Draft Thoughts", body="…",
        extra_fields={"status": "draft", "subtype": "note"},
    )
    api.patch(node["uid"], {"subtype": "essay"})

    assert node["uid"] not in {n["uid"] for n in graph.find(subtype="note")}
    assert [n["uid"] for n in graph.find(subtype="essay")] == [node["uid"]]


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def test_find_by_subtype_reads_the_fixture_vault(tmp_vault):
    graph.get(tmp_vault)
    chores = graph.find(node_type="task", subtype="chore")
    specs = graph.find(node_type="document", subtype="spec")

    assert [n["title"] for n in chores] == ["Review pull requests"]
    assert len(specs) == 2 and all(n["subtype"] == "spec" for n in specs)


def test_http_nodes_list_filters_by_subtype(tmp_vault, monkeypatch):
    from fastapi.testclient import TestClient
    from loci import http_server

    monkeypatch.setattr(http_server, "_API_TOKEN", "t")
    monkeypatch.setattr(http_server, "_allowed_origins", lambda: [])
    client = TestClient(http_server.app)

    rows = client.get("/api/nodes?type=task&subtype=chore", headers={"Authorization": "Bearer t"}).json()
    assert [r["title"] for r in rows] == ["Review pull requests"]
    assert rows[0]["subtype"] == "chore"


# ---------------------------------------------------------------------------
# Migration script
# ---------------------------------------------------------------------------

def _strip_subtypes(vault: Path) -> None:
    """Turn the fixture vault back into a pre-v2 vault: no subtypes, article `format`."""
    for path in vault.glob("*.md"):
        fm_text, body = split_frontmatter(path.read_text(encoding="utf-8"))
        fm = yaml.safe_load(fm_text)
        if fm.get("type") not in ("task", "document", "article"):
            continue
        sub = fm.pop("subtype", None)
        if fm["type"] == "article" and sub:
            fm["format"] = sub
        path.write_text("---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n" + body, encoding="utf-8")


def _fm(path: Path) -> dict:
    return yaml.safe_load(split_frontmatter(path.read_text(encoding="utf-8"))[0])


def test_migration_plan_is_a_dry_run_and_names_the_defaults(tmp_vault):
    _strip_subtypes(tmp_vault)
    before = {p.name: p.read_text() for p in tmp_vault.glob("*.md")}

    changes, unreadable = migrate_subtypes.plan_vault(tmp_vault)
    text = migrate_subtypes.report(changes, unreadable, applied=False)

    assert {p.name: p.read_text() for p in tmp_vault.glob("*.md")} == before
    assert unreadable == []
    assert {c.node_type for c in changes} == {"task", "document", "article"}
    assert "Dry run" in text
    defaulted = [c for c in changes if c.defaulted]
    assert defaulted and all(c.title in text for c in defaulted)


def test_migration_reads_tags_then_titles_then_defaults(tmp_path):
    cases = {
        "a.md": ({"type": "task", "title": "Anything", "tags": ["bug"]}, "bug", "tag:bug"),
        "b.md": ({"type": "task", "title": "Fix: the thing", "tags": []}, "bug", "title"),
        "c.md": ({"type": "task", "title": "Decide: where it lives", "tags": []}, "question", "title"),
        "d.md": ({"type": "task", "title": "Apply to the program", "tags": []}, "chore", "title"),
        "e.md": ({"type": "task", "title": "Add the widget", "tags": []}, "feature", "default"),
        "f.md": ({"type": "document", "title": "Sync with X", "tags": ["customer-meeting"]}, "meeting-notes", "tag:customer-meeting"),
        "g.md": ({"type": "document", "title": "Module 2 Lesson 3 Transcript", "tags": []}, "transcript", "title"),
        "h.md": ({"type": "document", "title": "Random thoughts", "tags": []}, "note", "default"),
        "i.md": ({"type": "article", "title": "A book", "format": "book", "tags": ["book"]}, "book", "format"),
    }
    for name, (fm, _, _) in cases.items():
        (tmp_path / name).write_text("---\n" + yaml.safe_dump(fm) + "---\nbody\n")

    changes = {c.path.name: c for c in migrate_subtypes.plan_vault(tmp_path)[0]}
    for name, (_, subtype, how) in cases.items():
        assert (changes[name].subtype, changes[name].how) == (subtype, how), name
    assert changes["a.md"].dropped_tags == ["bug"]
    assert changes["i.md"].dropped_tags == ["book"]


def test_migration_drops_only_the_tag_that_restates_the_chosen_subtype(tmp_path):
    cases = {
        # "feature X is broken": classified bug, the feature tag is still information
        "a.md": ({"type": "task", "title": "Broken", "tags": ["bug", "feature", "urgent"]}, ["bug"]),
        # first tag rule wins (plan); a report tag on a plan is not redundant
        "b.md": ({"type": "document", "title": "Q3", "tags": ["plan", "report"]}, ["plan"]),
        # aliases of the chosen subtype go too
        "c.md": ({"type": "document", "title": "Misc", "tags": ["notes", "note", "idea"]}, ["notes", "note"]),
        # article: only the tag matching the medium, not the whole vocabulary
        "d.md": ({"type": "article", "title": "Post", "format": "blog-post", "tags": ["technical", "blog-post"]}, ["blog-post"]),
    }
    for name, (fm, _) in cases.items():
        (tmp_path / name).write_text("---\n" + yaml.safe_dump(fm) + "---\nbody\n")

    changes = {c.path.name: c for c in migrate_subtypes.plan_vault(tmp_path)[0]}
    for name, (_, dropped) in cases.items():
        assert changes[name].dropped_tags == dropped, name

    migrate_subtypes.apply_vault(list(changes.values()))
    assert _fm(tmp_path / "a.md")["tags"] == ["feature", "urgent"]
    assert _fm(tmp_path / "d.md")["tags"] == ["technical"]


def test_migration_keeps_bare_timestamps_in_the_canonical_spelling(tmp_path):
    (tmp_path / "t.md").write_text(
        "---\ntype: task\ntitle: Anything\ncreated_at: 2026-01-01T00:00:00Z\n---\nbody\n"
    )
    changes, _ = migrate_subtypes.plan_vault(tmp_path)
    migrate_subtypes.apply_vault(changes)

    raw = (tmp_path / "t.md").read_text()
    assert "created_at: '2026-01-01T00:00:00Z'" in raw
    assert "2026-01-01 00:00:00" not in raw


def test_migration_apply_leaves_a_vault_the_linter_accepts(tmp_vault):
    _strip_subtypes(tmp_vault)
    assert lint_vault(tmp_vault)["errors"], "stripping subtypes should make the vault lint red"

    changes, _ = migrate_subtypes.plan_vault(tmp_vault)
    written = migrate_subtypes.apply_vault(changes)

    assert written == len(changes)
    codes = {e["code"] for e in lint_vault(tmp_vault)["errors"]}
    assert "missing-required-field" not in codes
    assert "invalid-enum" not in codes

    task = _fm(tmp_vault / "task-review-prs.md")
    article = _fm(tmp_vault / "article-ml-fundamentals.md")
    assert task["subtype"] == "feature"  # nothing in the title or tags says otherwise
    assert article["subtype"] == "article" and "format" not in article

    # Idempotent: a second plan finds nothing left to do.
    assert migrate_subtypes.plan_vault(tmp_vault)[0] == []


def test_migration_cli_refuses_a_missing_directory(tmp_path, capsys):
    assert migrate_subtypes.main([str(tmp_path / "nope")]) == 2
