"""Read/write/update the .inbox-plan.yaml work queue."""

import contextlib
import fcntl
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml


PLAN_FILENAME = ".inbox-plan.yaml"
_LOCK_FILENAME = ".inbox-plan.lock"

DEFAULT_BUDGET_FILES = 50
DEFAULT_BUDGET_CONTENT = 10


@contextlib.contextmanager
def _plan_lock(stage_root: Path):
    """Exclusive advisory lock for read-modify-write operations on the plan file."""
    lock_path = stage_root / _LOCK_FILENAME
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def _atomic_write(path: Path, content: str) -> None:
    """Write content to a temp file then rename over target (atomic on POSIX)."""
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def plan_path(stage_root: Path) -> Path:
    """Return the path to the plan file."""
    return stage_root / PLAN_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _recompute_progress(plan: dict) -> dict:
    """Recompute progress counts from items list. Returns updated plan (mutates in place)."""
    items = plan.get("items", [])

    file_items = [it for it in items if it.get("category") == "file"]
    content_items = [it for it in items if it.get("category") == "content"]

    def counts(lst: list) -> dict:
        total = len(lst)
        done = sum(1 for it in lst if it.get("status") == "done")
        failed = sum(1 for it in lst if it.get("status") == "failed")
        skipped = sum(1 for it in lst if it.get("status") == "skipped")
        pending = total - done - failed - skipped
        return {"total": total, "done": done, "failed": failed, "pending": pending}

    plan["progress"] = {
        "files": counts(file_items),
        "content": counts(content_items),
    }
    return plan


def write_plan(
    stage_root: Path,
    vault_root: Path,
    items: list,
    budget_files: int = DEFAULT_BUDGET_FILES,
    budget_content: int = DEFAULT_BUDGET_CONTENT,
) -> dict:
    """
    Write the plan file. Returns the plan dict.
    Items should already have 'status': 'pending' set (or will be forced here).
    """
    for item in items:
        item.setdefault("status", "pending")
        item.setdefault("result", None)

    total_files = sum(1 for it in items if it.get("category") == "file")
    total_content = sum(1 for it in items if it.get("category") == "content")

    runs_files = math.ceil(total_files / budget_files) if total_files else 0
    runs_content = math.ceil(total_content / budget_content) if total_content else 0

    plan: dict = {
        "version": 1,
        "created_at": _now(),
        "stage_root": str(stage_root),
        "vault_root": str(vault_root),
        "status": "pending",
        "budget_per_run": {
            "files": budget_files,
            "content": budget_content,
        },
        "progress": {
            "files": {
                "total": total_files,
                "done": 0,
                "failed": 0,
                "pending": total_files,
            },
            "content": {
                "total": total_content,
                "done": 0,
                "failed": 0,
                "pending": total_content,
            },
        },
        "items": items,
    }

    p = plan_path(stage_root)
    _atomic_write(p, yaml.dump(plan, sort_keys=False, allow_unicode=True))
    return plan


def read_plan(stage_root: Path) -> dict | None:
    """Return the plan dict, or None if no plan file exists."""
    p = plan_path(stage_root)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def approve_plan(stage_root: Path) -> dict:
    """Set plan status to 'approved'. Raises ValueError if no plan or already in progress/done."""
    with _plan_lock(stage_root):
        plan = read_plan(stage_root)
        if plan is None:
            raise ValueError("No plan file found. Run scan_inbox first.")
        status = plan.get("status", "pending")
        if status in ("in-progress", "done"):
            raise ValueError(f"Plan is already '{status}'. Cannot approve.")
        plan["status"] = "approved"
        _atomic_write(plan_path(stage_root), yaml.dump(plan, sort_keys=False, allow_unicode=True))
    return plan


def update_item_status(
    stage_root: Path,
    item_path: str,
    status: str,
    result: dict = None,
) -> None:
    """
    Find item by path, update status and result, recompute progress, write file.
    """
    with _plan_lock(stage_root):
        plan = read_plan(stage_root)
        if plan is None:
            raise ValueError("No plan file found.")

        items = plan.get("items", [])
        found = False
        for item in items:
            if item.get("path") == item_path:
                item["status"] = status
                item["result"] = result
                found = True
                break

        if not found:
            raise ValueError(f"Item not found in plan: {item_path!r}")

        _recompute_progress(plan)

        # Auto-advance plan status regardless of whether approve_plan() was called
        all_done_or_failed = all(
            it.get("status") in ("done", "failed", "skipped") for it in items
        )
        if all_done_or_failed and items:
            plan["status"] = "done"
        elif plan.get("status") in ("approved", "pending"):
            plan["status"] = "in-progress"

        _atomic_write(plan_path(stage_root), yaml.dump(plan, sort_keys=False, allow_unicode=True))


def get_pending_batch(plan: dict, category: str, limit: int) -> list[dict]:
    """Return next N pending items for the given category (file|content)."""
    items = plan.get("items", [])
    pending = [
        it for it in items
        if it.get("category") == category and it.get("status") == "pending"
    ]
    return pending[:limit]
