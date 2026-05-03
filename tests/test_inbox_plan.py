"""
tests/test_inbox_plan.py
Tests for tools/inbox_plan.py.
"""

import yaml
from pathlib import Path

import pytest

import inbox_plan as ip


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def stage_root(tmp_path):
    """Create a minimal loci-stage/ structure."""
    root = tmp_path / "loci-stage"
    root.mkdir()
    (root / "files").mkdir()
    (root / "unresolved").mkdir()
    return root


@pytest.fixture
def vault_root(tmp_path):
    return tmp_path / "knowledge-vault"


def _make_items(n_files=2, n_content=2):
    """Create a list of test items."""
    items = []
    for i in range(n_files):
        items.append({
            "id": i + 1,
            "path": f"files/book{i}.epub",
            "category": "file",
            "action": "ingest-asset",
            "type": "asset",
            "subtype": "book",
            "format": "epub",
            "mime_type": "application/epub+zip",
            "title": f"Book {i}",
        })
    for i in range(n_content):
        items.append({
            "id": n_files + i + 1,
            "path": f"note{i}.md",
            "category": "content",
            "action": "save-document",
            "type": "document",
            "format": "md",
            "mime_type": "text/markdown",
            "title": f"Note {i}",
        })
    return items


# ---------------------------------------------------------------------------
# plan_path
# ---------------------------------------------------------------------------

def test_plan_path_returns_correct_location(stage_root):
    p = ip.plan_path(stage_root)
    assert p == stage_root / ".inbox-plan.yaml"


# ---------------------------------------------------------------------------
# write_plan
# ---------------------------------------------------------------------------

def test_write_plan_creates_file(stage_root, vault_root):
    items = _make_items()
    ip.write_plan(stage_root, vault_root, items, [])
    p = ip.plan_path(stage_root)
    assert p.exists()


def test_write_plan_returns_plan_dict(stage_root, vault_root):
    items = _make_items(2, 3)
    plan = ip.write_plan(stage_root, vault_root, items, [])
    assert plan["version"] == 1
    assert plan["status"] == "pending"
    assert plan["progress"]["files"]["total"] == 2
    assert plan["progress"]["content"]["total"] == 3


def test_write_plan_sets_pending_status_on_items(stage_root, vault_root):
    items = _make_items(1, 0)
    plan = ip.write_plan(stage_root, vault_root, items, [])
    for item in plan["items"]:
        assert item["status"] == "pending"
        assert item["result"] is None


def test_write_plan_includes_unresolved(stage_root, vault_root):
    unresolved = [{"path": "files/thesis.pdf", "reason": "ambiguous", "options": []}]
    plan = ip.write_plan(stage_root, vault_root, [], unresolved)
    assert len(plan["unresolved"]) == 1
    assert plan["unresolved"][0]["path"] == "files/thesis.pdf"


def test_write_plan_yaml_is_valid(stage_root, vault_root):
    items = _make_items()
    ip.write_plan(stage_root, vault_root, items, [])
    content = ip.plan_path(stage_root).read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict)
    assert "items" in parsed


# ---------------------------------------------------------------------------
# read_plan
# ---------------------------------------------------------------------------

def test_read_plan_returns_none_when_no_file(stage_root):
    result = ip.read_plan(stage_root)
    assert result is None


def test_read_plan_returns_written_plan(stage_root, vault_root):
    items = _make_items(1, 1)
    ip.write_plan(stage_root, vault_root, items, [])
    plan = ip.read_plan(stage_root)
    assert plan is not None
    assert plan["version"] == 1
    assert len(plan["items"]) == 2


# ---------------------------------------------------------------------------
# approve_plan
# ---------------------------------------------------------------------------

def test_approve_plan_changes_status(stage_root, vault_root):
    items = _make_items()
    ip.write_plan(stage_root, vault_root, items, [])
    plan = ip.approve_plan(stage_root)
    assert plan["status"] == "approved"


def test_approve_plan_persists_to_file(stage_root, vault_root):
    items = _make_items()
    ip.write_plan(stage_root, vault_root, items, [])
    ip.approve_plan(stage_root)
    plan = ip.read_plan(stage_root)
    assert plan["status"] == "approved"


def test_approve_plan_raises_when_no_plan(stage_root):
    with pytest.raises(ValueError, match="No plan file found"):
        ip.approve_plan(stage_root)


def test_approve_plan_raises_when_in_progress(stage_root, vault_root):
    items = _make_items(1, 0)
    ip.write_plan(stage_root, vault_root, items, [])
    ip.approve_plan(stage_root)
    # Manually mark in-progress
    plan = ip.read_plan(stage_root)
    plan["status"] = "in-progress"
    ip.plan_path(stage_root).write_text(
        yaml.dump(plan, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="in-progress"):
        ip.approve_plan(stage_root)


def test_approve_plan_raises_when_done(stage_root, vault_root):
    items = _make_items(1, 0)
    ip.write_plan(stage_root, vault_root, items, [])
    plan = ip.read_plan(stage_root)
    plan["status"] = "done"
    ip.plan_path(stage_root).write_text(
        yaml.dump(plan, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="done"):
        ip.approve_plan(stage_root)


# ---------------------------------------------------------------------------
# update_item_status
# ---------------------------------------------------------------------------

def test_update_item_status_changes_status(stage_root, vault_root):
    items = _make_items(1, 0)
    ip.write_plan(stage_root, vault_root, items, [])
    ip.approve_plan(stage_root)
    ip.update_item_status(stage_root, "files/book0.epub", "done", {"uid": "abc12345"})
    plan = ip.read_plan(stage_root)
    item = plan["items"][0]
    assert item["status"] == "done"
    assert item["result"]["uid"] == "abc12345"


def test_update_item_status_recomputes_progress(stage_root, vault_root):
    items = _make_items(2, 0)
    ip.write_plan(stage_root, vault_root, items, [])
    ip.approve_plan(stage_root)
    ip.update_item_status(stage_root, "files/book0.epub", "done", {"uid": "aaa"})
    plan = ip.read_plan(stage_root)
    assert plan["progress"]["files"]["done"] == 1
    assert plan["progress"]["files"]["pending"] == 1


def test_update_item_status_raises_when_not_found(stage_root, vault_root):
    items = _make_items(1, 0)
    ip.write_plan(stage_root, vault_root, items, [])
    with pytest.raises(ValueError, match="not found"):
        ip.update_item_status(stage_root, "nonexistent.epub", "done")


def test_update_item_status_advances_to_in_progress(stage_root, vault_root):
    items = _make_items(2, 0)
    ip.write_plan(stage_root, vault_root, items, [])
    ip.approve_plan(stage_root)
    ip.update_item_status(stage_root, "files/book0.epub", "done")
    plan = ip.read_plan(stage_root)
    # Still has one pending item, so status should move to in-progress
    assert plan["status"] == "in-progress"


def test_update_item_status_done_when_all_complete(stage_root, vault_root):
    items = _make_items(1, 0)
    ip.write_plan(stage_root, vault_root, items, [])
    ip.approve_plan(stage_root)
    ip.update_item_status(stage_root, "files/book0.epub", "done")
    plan = ip.read_plan(stage_root)
    assert plan["status"] == "done"


# ---------------------------------------------------------------------------
# get_pending_batch
# ---------------------------------------------------------------------------

def test_get_pending_batch_returns_correct_items(stage_root, vault_root):
    items = _make_items(5, 3)
    plan = ip.write_plan(stage_root, vault_root, items, [])
    batch = ip.get_pending_batch(plan, "file", 3)
    assert len(batch) == 3
    assert all(it["category"] == "file" for it in batch)


def test_get_pending_batch_respects_limit(stage_root, vault_root):
    items = _make_items(10, 0)
    plan = ip.write_plan(stage_root, vault_root, items, [])
    batch = ip.get_pending_batch(plan, "file", 5)
    assert len(batch) == 5


def test_get_pending_batch_skips_non_pending(stage_root, vault_root):
    items = _make_items(3, 0)
    plan = ip.write_plan(stage_root, vault_root, items, [])
    # Mark first item as done
    plan["items"][0]["status"] = "done"
    batch = ip.get_pending_batch(plan, "file", 10)
    assert len(batch) == 2
    assert all(it["status"] == "pending" for it in batch)


def test_get_pending_batch_empty_when_all_done(stage_root, vault_root):
    items = _make_items(2, 0)
    plan = ip.write_plan(stage_root, vault_root, items, [])
    for item in plan["items"]:
        item["status"] = "done"
    batch = ip.get_pending_batch(plan, "file", 10)
    assert batch == []


def test_get_pending_batch_content_category(stage_root, vault_root):
    items = _make_items(2, 4)
    plan = ip.write_plan(stage_root, vault_root, items, [])
    batch = ip.get_pending_batch(plan, "content", 3)
    assert len(batch) == 3
    assert all(it["category"] == "content" for it in batch)


# ---------------------------------------------------------------------------
# _recompute_progress
# ---------------------------------------------------------------------------

def test_recompute_progress_correct_counts():
    plan = {
        "items": [
            {"category": "file", "status": "done"},
            {"category": "file", "status": "pending"},
            {"category": "file", "status": "failed"},
            {"category": "content", "status": "pending"},
            {"category": "content", "status": "done"},
        ]
    }
    updated = ip._recompute_progress(plan)
    assert updated["progress"]["files"]["total"] == 3
    assert updated["progress"]["files"]["done"] == 1
    assert updated["progress"]["files"]["failed"] == 1
    assert updated["progress"]["files"]["pending"] == 1
    assert updated["progress"]["content"]["total"] == 2
    assert updated["progress"]["content"]["done"] == 1
    assert updated["progress"]["content"]["pending"] == 1


# ---------------------------------------------------------------------------
# resolve_unresolved_item
# ---------------------------------------------------------------------------

def test_resolve_unresolved_item_moves_to_items(stage_root, vault_root):
    unresolved = [
        {"path": "files/thesis.pdf", "reason": "ambiguous", "options": [
            {"action": "ingest-asset", "type": "asset", "subtype": "book"},
        ]}
    ]
    ip.write_plan(stage_root, vault_root, [], unresolved)

    # Create the actual file so metadata can be extracted
    (stage_root / "files").mkdir(exist_ok=True)
    (stage_root / "files" / "thesis.pdf").write_bytes(b"fake pdf")

    plan = ip.resolve_unresolved_item(
        stage_root, "files/thesis.pdf", "ingest-asset", "asset", "book"
    )
    assert len(plan["unresolved"]) == 0
    assert len(plan["items"]) == 1
    assert plan["items"][0]["path"] == "files/thesis.pdf"
    assert plan["items"][0]["action"] == "ingest-asset"
    assert plan["items"][0]["subtype"] == "book"


def test_resolve_unresolved_raises_when_not_found(stage_root, vault_root):
    ip.write_plan(stage_root, vault_root, [], [])
    with pytest.raises(ValueError, match="not found"):
        ip.resolve_unresolved_item(stage_root, "nonexistent.pdf", "ingest-asset", "asset")
