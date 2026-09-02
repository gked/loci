"""
tests/test_write_file.py
Tests for tools/write_file.py: frontmatter serialization, write_item,
patch_item, and check_duplicate.
"""

import yaml
import pytest
from pathlib import Path
from datetime import datetime, timezone

from loci.tools.write_file import (
    serialize_frontmatter,
    write_item,
    patch_item,
    check_duplicate,
    validate_required_fields,
)
from loci.tools.type_registry import TypeRegistry, REFERENCES_DIR
from loci.tools.frontmatter import split_frontmatter


# ---------------------------------------------------------------------------
# serialize_frontmatter
# ---------------------------------------------------------------------------

def test_serialize_frontmatter_produces_yaml_block():
    result = serialize_frontmatter({"uid": "abc12345", "type": "document", "title": "T"})
    assert result.startswith("---\n")
    assert result.endswith("---\n")
    parsed = yaml.safe_load(result.strip("---\n"))
    assert parsed == {"uid": "abc12345", "type": "document", "title": "T"}


def test_serialize_frontmatter_unicode():
    result = serialize_frontmatter({"title": "Привет мир"})
    assert "Привет мир" in result


# ---------------------------------------------------------------------------
# write_item
# ---------------------------------------------------------------------------

def test_write_item_creates_file(tmp_vault):
    result = write_item(
        type="document",
        title="Hello World",
        body="Some body text.",
        extra_fields={"status": "draft"},
        skip_duplicate_check=True,
    )
    assert result["type"] == "document"
    assert result["title"] == "Hello World"
    p = Path(result["path"])
    assert p.exists()
    raw = p.read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    assert "Hello World" in raw


def test_write_item_frontmatter_fields(tmp_vault):
    result = write_item(
        type="task",
        title="My Task",
        body="Do something.",
        tags=["python", "testing"],
        domains=["engineering"],
        summary="A test task.",
        extra_fields={"status": "todo"},
        skip_duplicate_check=True,
    )
    raw = Path(result["path"]).read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert fm["type"] == "task"
    assert fm["tags"] == ["python", "testing"]
    assert fm["domains"] == ["engineering"]
    assert fm["summary"] == "A test task."
    assert len(fm["uid"]) == 8


def test_write_item_body_follows_frontmatter(tmp_vault):
    result = write_item(
        type="document",
        title="Body Test",
        body="This is the body.",
        extra_fields={"status": "draft"},
        skip_duplicate_check=True,
    )
    raw = Path(result["path"]).read_text(encoding="utf-8")
    body_part = raw.split("---", 2)[2]
    assert "This is the body." in body_part


def test_write_item_extra_fields_merged(tmp_vault):
    result = write_item(
        type="document",
        title="Asset Doc",
        body="",
        extra_fields={"status": "draft", "has_asset": True, "uid": "fixed001"},
        skip_duplicate_check=True,
    )
    raw = Path(result["path"]).read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert fm["has_asset"] is True
    assert fm["uid"] == "fixed001"


def test_write_item_invalid_type_raises(tmp_vault):
    with pytest.raises(ValueError, match="Unknown type"):
        write_item(type="banana", title="T", body="", skip_duplicate_check=True)


def test_write_item_sets_state_active(tmp_vault):
    result = write_item(
        type="document",
        title="State Test",
        body="",
        extra_fields={"status": "draft"},
        skip_duplicate_check=True,
    )
    raw = Path(result["path"]).read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert fm["state"] == "active"


# ---------------------------------------------------------------------------
# patch_item
# ---------------------------------------------------------------------------

def _make_vault_file(tmp_vault: Path, uid: str = "test0001") -> Path:
    """Write a minimal vault file and return its path."""
    p = tmp_vault / f"{uid}-test-note.md"
    fm = {
        "uid": uid,
        "type": "document",
        "title": "Original Title",
        "tags": ["old-tag"],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    p.write_text("---\n" + yaml.dump(fm) + "---\n\nOriginal body.", encoding="utf-8")
    return p


def test_patch_item_merges_updates(tmp_vault):
    p = _make_vault_file(tmp_vault)
    result = patch_item(str(p), {"tags": ["new-tag"], "status": "done"})
    raw = p.read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert fm["tags"] == ["new-tag"]
    assert fm["status"] == "done"
    assert fm["uid"] == "test0001"  # original field preserved
    assert result["uid"] == "test0001"


def test_patch_item_bumps_updated_at(tmp_vault):
    p = _make_vault_file(tmp_vault)
    # Truncate to seconds to match strftime("%Y-%m-%dT%H:%M:%SZ") precision
    before = datetime.now(timezone.utc).replace(microsecond=0)
    patch_item(str(p), {"title": "Updated"})
    raw = p.read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    updated = datetime.fromisoformat(fm["updated_at"].replace("Z", "+00:00"))
    assert updated >= before


def test_patch_item_preserves_body_by_default(tmp_vault):
    p = _make_vault_file(tmp_vault)
    patch_item(str(p), {"title": "Changed"})
    raw = p.read_text(encoding="utf-8")
    assert "Original body." in raw


def test_patch_item_replaces_body_when_provided(tmp_vault):
    p = _make_vault_file(tmp_vault)
    patch_item(str(p), {}, body="New body content.")
    raw = p.read_text(encoding="utf-8")
    assert "New body content." in raw
    assert "Original body." not in raw


def test_patch_item_file_without_frontmatter_delimiter(tmp_vault):
    """patch_item on a file that doesn't start with --- treats whole content as body."""
    p = tmp_vault / "plain.md"
    p.write_text("Just plain text body.\n", encoding="utf-8")
    result = patch_item(str(p), {"title": "New Title"})
    assert result["title"] == "New Title"
    raw = p.read_text(encoding="utf-8")
    assert "Just plain text body." in raw


def test_patch_item_incomplete_frontmatter_delimiter(tmp_vault):
    """patch_item on a file with opening --- but no closing --- treats whole content as body."""
    p = tmp_vault / "bad-fm.md"
    p.write_text("---\nno closing delimiter content\n", encoding="utf-8")
    result = patch_item(str(p), {"title": "Patched"})
    assert result["title"] == "Patched"


def test_patch_item_missing_file_raises(tmp_vault):
    with pytest.raises(FileNotFoundError):
        patch_item(str(tmp_vault / "nonexistent.md"), {})


def test_patch_item_returns_metadata(tmp_vault):
    p = _make_vault_file(tmp_vault)
    result = patch_item(str(p), {"title": "New Title"})
    assert result["uid"] == "test0001"
    assert result["title"] == "New Title"
    assert result["type"] == "document"
    assert result["path"] == str(p)


def test_patch_item_datetime_strings_preserved(tmp_vault):
    """yaml.safe_load parses bare datetime values as Python datetime objects;
    patch_item must convert them back to ISO strings before writing."""
    p = tmp_vault / "datetime-test.md"
    # Write timestamps without quotes so yaml.safe_load will parse them as datetime objects
    p.write_text(
        "---\nuid: dt000001\ntype: document\ntitle: DT Test\n"
        "created_at: 2026-01-01T00:00:00Z\nupdated_at: 2026-01-01T00:00:00Z\n---\n\nBody.",
        encoding="utf-8",
    )
    patch_item(str(p), {"title": "Patched"})
    raw = p.read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert isinstance(fm["created_at"], str), "created_at should be a string, not a datetime object"
    assert fm["created_at"] == "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# check_duplicate
# ---------------------------------------------------------------------------

def test_check_duplicate_matches_title_slug(tmp_vault):
    # The fixture vault has "doc-testing-strategies.md"
    match = check_duplicate(tmp_vault, "testing strategies")
    assert match is not None
    assert "testing-strategies" in match.name


def test_check_duplicate_matches_url_in_content(tmp_vault):
    p = tmp_vault / "bookmark-test.md"
    p.write_text(
        "---\nuid: bkm00001\ntype: bookmark\ntitle: Example\n---\n\nhttps://example.com/article",
        encoding="utf-8",
    )
    match = check_duplicate(tmp_vault, "something new", url="https://example.com/article")
    assert match is not None
    assert match.name == "bookmark-test.md"


def test_check_duplicate_returns_none_when_no_match(tmp_vault):
    match = check_duplicate(tmp_vault, "totally unique xyzzy12345")
    assert match is None


# ---------------------------------------------------------------------------
# resolve_vault_root — error path
# ---------------------------------------------------------------------------

def test_resolve_vault_root_raises_when_no_config(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)
    monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / "nonexistent.yml"))
    from loci.tools.write_file import resolve_vault_root
    with pytest.raises(RuntimeError, match="set_vault_root"):
        resolve_vault_root()


# ---------------------------------------------------------------------------
# write_item — interactive duplicate check
# ---------------------------------------------------------------------------

def test_write_item_references_url_used_for_duplicate_check(tmp_vault, monkeypatch):
    """write_item extracts URL from references[0] when checking duplicates."""
    # First write a bookmark with a URL in its body so check_duplicate can find it by URL
    existing = tmp_vault / "bkm-existing.md"
    existing.write_text(
        "---\nuid: bkm00099\ntype: bookmark\ntitle: Old Bookmark\n---\n\nhttps://example.com/ref-test",
        encoding="utf-8",
    )
    monkeypatch.setattr("builtins.input", lambda: "n")
    result = write_item(
        type="bookmark",
        title="New Bookmark Different Title",
        body="",
        extra_fields={"source_url": "https://example.com/ref-test"},
        references=[{"url": "https://example.com/ref-test", "title": "Example", "source_type": "web"}],
    )
    # URL match found → user typed "n" → write aborted
    assert result == {}


def test_write_item_duplicate_check_aborted(tmp_vault, monkeypatch):
    # Create a file that will be detected as a duplicate
    write_item(type="document", title="Duplicate Title", body="", extra_fields={"status": "draft"}, skip_duplicate_check=True)
    monkeypatch.setattr("builtins.input", lambda: "n")
    result = write_item(type="document", title="Duplicate Title", body="", extra_fields={"status": "draft"})
    assert result == {}


def test_write_item_duplicate_check_confirmed(tmp_vault, monkeypatch):
    write_item(type="document", title="Dup Confirmed", body="", extra_fields={"status": "draft"}, skip_duplicate_check=True)
    monkeypatch.setattr("builtins.input", lambda: "y")
    result = write_item(type="document", title="Dup Confirmed", body="", extra_fields={"status": "draft"})
    assert result.get("uid") is not None


# ---------------------------------------------------------------------------
# validate_required_fields
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registry():
    return TypeRegistry.load(REFERENCES_DIR / "ontology.yaml")


def test_validate_required_fields_valid_task(registry):
    type_def = registry.get("task")
    errors = validate_required_fields(type_def, {"status": "todo"})
    assert errors == []


def test_validate_required_fields_missing_required(registry):
    type_def = registry.get("task")
    errors = validate_required_fields(type_def, {})
    assert any("status" in e for e in errors)


def test_validate_required_fields_null_required(registry):
    type_def = registry.get("task")
    errors = validate_required_fields(type_def, {"status": None})
    assert any("status" in e for e in errors)


def test_validate_required_fields_invalid_enum(registry):
    type_def = registry.get("task")
    errors = validate_required_fields(type_def, {"status": "blocked"})
    assert any("blocked" in e for e in errors)
    assert any("status" in e for e in errors)


def test_validate_required_fields_valid_enum_duplicate(registry):
    type_def = registry.get("task")
    errors = validate_required_fields(type_def, {"status": "duplicate"})
    assert errors == []


def test_validate_required_fields_invalid_optional_enum(registry):
    type_def = registry.get("task")
    errors = validate_required_fields(type_def, {"status": "todo", "priority": "critical"})
    assert any("priority" in e for e in errors)
    assert any("critical" in e for e in errors)


def test_validate_required_fields_valid_optional_enum(registry):
    type_def = registry.get("task")
    errors = validate_required_fields(type_def, {"status": "todo", "priority": "high"})
    assert errors == []


def test_validate_required_fields_entity_missing_subtype(registry):
    type_def = registry.get("entity")
    errors = validate_required_fields(type_def, {})
    assert any("subtype" in e for e in errors)


def test_validate_required_fields_entity_invalid_subtype(registry):
    type_def = registry.get("entity")
    errors = validate_required_fields(type_def, {"subtype": "robot"})
    assert any("subtype" in e for e in errors)


def test_validate_required_fields_no_type_specific_fields(registry):
    """document has status as required; empty extra_fields triggers an error."""
    type_def = registry.get("document")
    errors = validate_required_fields(type_def, {})
    assert any("status" in e for e in errors)


# ---------------------------------------------------------------------------
# write_item — required field validation integration
# ---------------------------------------------------------------------------

def test_write_item_returns_errors_when_required_field_missing(tmp_vault):
    result = write_item(
        type="task",
        title="Missing Status",
        body="",
        skip_duplicate_check=True,
        # no extra_fields → status missing
    )
    assert "errors" in result
    assert any("status" in e for e in result["errors"])


def test_write_item_returns_errors_for_invalid_enum(tmp_vault):
    result = write_item(
        type="task",
        title="Bad Status",
        body="",
        extra_fields={"status": "blocked"},
        skip_duplicate_check=True,
    )
    assert "errors" in result
    assert any("blocked" in e for e in result["errors"])


def test_write_item_book_invalid_genre_blocked(tmp_vault):
    result = write_item(
        type="asset",
        title="Bad Genre Book",
        body="",
        extra_fields={"subtype": "book", "genre": "cooking"},
        skip_duplicate_check=True,
    )
    assert "errors" in result
    assert any("genre" in e for e in result["errors"])


def test_write_item_book_valid_genre_succeeds(tmp_vault):
    result = write_item(
        type="asset",
        title="Good Genre Book",
        body="",
        extra_fields={"subtype": "book", "genre": "technology-computing"},
        skip_duplicate_check=True,
    )
    assert "errors" not in result
    assert result.get("uid") is not None


def test_write_item_non_book_asset_genre_not_validated(tmp_vault):
    result = write_item(
        type="asset",
        title="Video With Genre",
        body="",
        extra_fields={"subtype": "video", "genre": "cooking"},
        skip_duplicate_check=True,
    )
    assert "errors" not in result


def test_write_item_succeeds_with_valid_required_fields(tmp_vault):
    result = write_item(
        type="task",
        title="Valid Task",
        body="",
        extra_fields={"status": "todo"},
        skip_duplicate_check=True,
    )
    assert "errors" not in result
    assert result.get("uid") is not None


def test_write_item_no_file_written_on_validation_error(tmp_vault):
    before = list(tmp_vault.glob("*.md"))
    write_item(
        type="task",
        title="Should Not Write",
        body="",
        skip_duplicate_check=True,
    )
    after = list(tmp_vault.glob("*.md"))
    assert len(after) == len(before)


# ---------------------------------------------------------------------------
# write_item — relation type validation
# ---------------------------------------------------------------------------

def test_write_item_blocked_by_unknown_relation_type(tmp_vault):
    result = write_item(
        type="document",
        title="Doc with Bad Relation",
        body="",
        extra_fields={"status": "draft"},
        relations=[{"uid": "deadbeef", "type": "invented-type"}],
        skip_duplicate_check=True,
    )
    assert "errors" in result
    assert any("invented-type" in e for e in result["errors"])


def test_write_item_no_file_written_on_bad_relation_type(tmp_vault):
    before = list(tmp_vault.glob("*.md"))
    write_item(
        type="document",
        title="Bad Relation Doc",
        body="",
        extra_fields={"status": "draft"},
        relations=[{"uid": "deadbeef", "type": "invented-type"}],
        skip_duplicate_check=True,
    )
    after = list(tmp_vault.glob("*.md"))
    assert len(after) == len(before)


def test_write_item_succeeds_with_valid_relation_type(tmp_vault):
    result = write_item(
        type="document",
        title="Doc with Valid Relation",
        body="",
        extra_fields={"status": "draft"},
        relations=[{"uid": "deadbeef", "type": "belongs-to"}],
        skip_duplicate_check=True,
    )
    assert "errors" not in result
    assert result.get("uid") is not None


# ---------------------------------------------------------------------------
# patch_item — relation type validation
# ---------------------------------------------------------------------------

def test_patch_item_warns_on_unknown_relation_type(tmp_vault):
    p = _make_vault_file(tmp_vault)
    result = patch_item(str(p), {"relations": [{"uid": "deadbeef", "type": "invented-type"}]})
    assert "relation_warnings" in result
    assert any("invented-type" in w for w in result["relation_warnings"])


def test_patch_item_still_writes_on_unknown_relation_type(tmp_vault):
    p = _make_vault_file(tmp_vault)
    result = patch_item(str(p), {"relations": [{"uid": "deadbeef", "type": "invented-type"}]})
    assert result.get("uid") == "test0001"
    raw = p.read_text(encoding="utf-8")
    assert "invented-type" in raw


def test_patch_item_no_relation_warnings_for_valid_type(tmp_vault):
    p = _make_vault_file(tmp_vault)
    result = patch_item(str(p), {"relations": [{"uid": "deadbeef", "type": "belongs-to"}]})
    assert "relation_warnings" not in result


# ---------------------------------------------------------------------------
# patch_item — 'body' passed inside updates
#
# This is how vault nodes got corrupted: body merged into the frontmatter dict
# and serialised as a quoted scalar. When that body contained a '---' line the
# node stopped parsing for every reader at once.
# ---------------------------------------------------------------------------

def test_patch_item_reroutes_body_from_updates_to_the_body(tmp_vault):
    p = _make_vault_file(tmp_vault)
    result = patch_item(str(p), {"body": "Replacement body."})

    raw = p.read_text(encoding="utf-8")
    fm_text, body = split_frontmatter(raw)
    fm = yaml.safe_load(fm_text)

    assert "body" not in fm
    assert body.strip() == "Replacement body."
    assert any("body" in w for w in result["body_warnings"])


def test_patch_item_body_argument_wins_over_updates_copy(tmp_vault):
    p = _make_vault_file(tmp_vault)
    result = patch_item(str(p), {"body": "From updates."}, body="From the argument.")

    fm_text, body = split_frontmatter(p.read_text(encoding="utf-8"))
    assert "body" not in yaml.safe_load(fm_text)
    assert body.strip() == "From the argument."
    assert any("argument won" in w for w in result["body_warnings"])


def test_patch_item_body_in_updates_never_reaches_the_frontmatter(tmp_vault):
    """The corruption case: a body containing a '---' line must stay out of the block."""
    p = _make_vault_file(tmp_vault)
    patch_item(str(p), {"body": "Intro.\n\n---\n\nAfter the rule."})

    raw = p.read_text(encoding="utf-8")
    fm_text, body = split_frontmatter(raw)
    assert fm_text is not None
    assert "body" not in yaml.safe_load(fm_text)
    assert "After the rule." in body


def test_patch_item_without_body_key_emits_no_body_warnings(tmp_vault):
    p = _make_vault_file(tmp_vault)
    result = patch_item(str(p), {"tags": ["x"]})
    assert "body_warnings" not in result


def test_patch_item_does_not_mutate_the_callers_updates_dict(tmp_vault):
    p = _make_vault_file(tmp_vault)
    updates = {"body": "New body.", "tags": ["x"]}
    patch_item(str(p), updates)
    assert updates == {"body": "New body.", "tags": ["x"]}


def test_patch_item_null_body_in_updates_clears_the_body(tmp_vault):
    """A null must not report success while silently keeping the old body."""
    p = _make_vault_file(tmp_vault)
    result = patch_item(str(p), {"body": None})

    fm_text, body = split_frontmatter(p.read_text(encoding="utf-8"))
    assert "body" not in yaml.safe_load(fm_text)
    assert body.strip() == ""
    assert any("cleared" in w for w in result["body_warnings"])


# ---------------------------------------------------------------------------
# patch_item — repairing a node already carrying a 'body' key
#
# The reroute above stops new damage. These cover the nodes damaged before it
# existed: without the strip, patch_vault is the tool that caused the
# corruption and also the only tool that cannot undo it.
# ---------------------------------------------------------------------------

def _make_corrupt_vault_file(tmp_vault: Path, uid: str = "test0002") -> Path:
    """Write a vault file whose frontmatter wrongly carries a 'body' key."""
    p = tmp_vault / f"{uid}-corrupt-note.md"
    fm = {
        "uid": uid,
        "type": "document",
        "title": "Corrupt Note",
        "tags": ["old-tag"],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "body": "Stale body.\n\n---\n\nAfter the rule.",
    }
    p.write_text("---\n" + yaml.dump(fm) + "---\n\nReal body.", encoding="utf-8")
    return p


def test_patch_item_strips_a_stale_body_key_from_the_frontmatter(tmp_vault):
    p = _make_corrupt_vault_file(tmp_vault)
    result = patch_item(str(p), {"body": "Repaired body."})

    fm_text, body = split_frontmatter(p.read_text(encoding="utf-8"))
    assert "body" not in yaml.safe_load(fm_text)
    assert body.strip() == "Repaired body."
    assert any("stale" in w for w in result["body_warnings"])


def test_patch_item_strips_stale_body_key_on_an_unrelated_patch(tmp_vault):
    """Repair must not require the caller to know the node is damaged."""
    p = _make_corrupt_vault_file(tmp_vault)
    result = patch_item(str(p), {"tags": ["new-tag"]})

    fm_text, body = split_frontmatter(p.read_text(encoding="utf-8"))
    fm = yaml.safe_load(fm_text)
    assert "body" not in fm
    assert fm["tags"] == ["new-tag"]
    assert body.strip() == "Real body."
    assert any("stale" in w for w in result["body_warnings"])


# ---------------------------------------------------------------------------
# write_item — 'body' passed inside extra_fields
#
# Same corruption vector as patch_item's updates, on the save path.
# ---------------------------------------------------------------------------

def test_write_item_reroutes_body_from_extra_fields(tmp_vault):
    result = write_item(
        type="document",
        title="Rerouted Body",
        body="",
        extra_fields={"status": "draft", "body": "Body from extra_fields."},
        skip_duplicate_check=True,
    )

    fm_text, body = split_frontmatter(Path(result["path"]).read_text(encoding="utf-8"))
    assert "body" not in yaml.safe_load(fm_text)
    assert body.strip() == "Body from extra_fields."
    assert any("extra_fields" in w for w in result["body_warnings"])


def test_write_item_body_argument_wins_over_extra_fields_copy(tmp_vault):
    result = write_item(
        type="document",
        title="Argument Wins",
        body="Real body.",
        extra_fields={"status": "draft", "body": "Body from extra_fields."},
        skip_duplicate_check=True,
    )

    fm_text, body = split_frontmatter(Path(result["path"]).read_text(encoding="utf-8"))
    assert "body" not in yaml.safe_load(fm_text)
    assert body.strip() == "Real body."
    assert any("argument won" in w for w in result["body_warnings"])


def test_write_item_body_in_extra_fields_never_reaches_the_frontmatter(tmp_vault):
    """The corruption case on save: a '---' in the body must not split the node."""
    result = write_item(
        type="document",
        title="Rule In Body",
        body="",
        extra_fields={"status": "draft", "body": "Intro.\n\n---\n\nAfter the rule."},
        skip_duplicate_check=True,
    )

    fm_text, body = split_frontmatter(Path(result["path"]).read_text(encoding="utf-8"))
    assert fm_text is not None
    fm = yaml.safe_load(fm_text)
    assert "body" not in fm
    assert fm["title"] == "Rule In Body"
    assert "After the rule." in body


def test_write_item_without_body_in_extra_fields_emits_no_body_warnings(tmp_vault):
    result = write_item(
        type="document",
        title="Clean Save",
        body="Just a body.",
        extra_fields={"status": "draft"},
        skip_duplicate_check=True,
    )
    assert "body_warnings" not in result


def test_write_item_does_not_mutate_the_callers_extra_fields_dict(tmp_vault):
    extra = {"status": "draft", "body": "Body from extra_fields."}
    write_item(
        type="document",
        title="No Mutation",
        body="",
        extra_fields=extra,
        skip_duplicate_check=True,
    )
    assert extra == {"status": "draft", "body": "Body from extra_fields."}
