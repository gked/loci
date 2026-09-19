"""
scripts/migrate_subtypes.py
Give every task, document, and article in a vault a `subtype`.

ontology_version 2 made `subtype` a required enum on task and document and
renamed article's `format` to `subtype`. A vault written before that lints
red on every one of those nodes until each carries a value. This script
assigns one, from what the node already says about itself:

  * article — `format` is renamed to `subtype`, value unchanged. An article
    with neither gets `article`.
  * task — a tag or a title prefix that names the kind wins (`bug`, "Fix: …",
    `open-question`, "Decide …", "Investigate …", …); otherwise `feature`.
  * document — likewise (`customer-meeting` → meeting-notes, `interview-snapshot`
    → report, "… Design Spec" → spec, …); otherwise `note`.

Tags that only restated the subtype (`bug`, `open-question`, `meeting-notes`,
`book` on an article, …) are dropped, because the rule that introduced
subtypes is that a subtype is never duplicated as a tag.

Nothing is written unless `--apply` is given. The dry run prints the plan and,
separately, the nodes that fell through to the default — those are the ones
worth a look, because the default is a guess, not a reading of the node.

Usage:
    uv run python scripts/migrate_subtypes.py <vault-root>            # plan only
    uv run python scripts/migrate_subtypes.py <vault-root> --apply    # write
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from loci.tools.frontmatter import split_frontmatter
from loci.tools.write_file import serialize_frontmatter

# Order matters within each list: the first rule that matches decides. Tags
# are checked before titles, since a tag was a deliberate label and a title
# prefix is a habit.

TASK_DEFAULT = "feature"
TASK_BY_TAG = [
    ({"bug", "bugs", "defect"}, "bug"),
    ({"open-question", "open-questions", "question", "decision", "investigation", "research-question"}, "question"),
    ({"chore", "admin", "housekeeping", "errand"}, "chore"),
    ({"feature", "enhancement"}, "feature"),
]
TASK_BY_TITLE = [
    (re.compile(r"^(bug|fix)\b", re.I), "bug"),
    (re.compile(r"^(open question|decide|decision|investigate|think through|should we|evaluate|explore|research|consider|reconsider|analy[sz]e|define|design .* principles)\b", re.I), "question"),
    (re.compile(r"^(apply to|register|withdraw|renew|pay|file|submit|sign up|cancel|finish registration|follow up|appeal|get approved|sync with|update .* (filing|registration))\b", re.I), "chore"),
]

DOCUMENT_DEFAULT = "note"
DOCUMENT_BY_TAG = [
    ({"meeting-notes", "meeting", "customer-meeting", "1-1", "1-on-1", "sync", "meeting-prep"}, "meeting-notes"),
    ({"transcript", "lesson-transcript", "coursera", "lecture"}, "transcript"),
    ({"spec", "design-spec", "design-doc", "requirements", "architecture-doc"}, "spec"),
    ({"plan", "project-plan", "dev-plan", "playbook", "roadmap", "implementation-plan"}, "plan"),
    ({"report", "interview-snapshot", "signal-report", "research-findings", "survey-report", "readout", "session-summary", "findings"}, "report"),
    ({"essay", "blog-post", "writing", "article-draft"}, "essay"),
    ({"journal", "diary", "daily"}, "journal"),
    ({"note", "notes"}, "note"),
]
DOCUMENT_BY_TITLE = [
    (re.compile(r"\b(meeting notes|meeting prep|1[-: ]?1 with|sync|intro (call|meeting)|discussion)\b", re.I), "meeting-notes"),
    (re.compile(r"\btranscript\b", re.I), "transcript"),
    (re.compile(r"\b(design spec|spec|requirements|design(?! review)|architecture|schema)\b", re.I), "spec"),
    (re.compile(r"\b(plan|playbook|roadmap|handoff)\b", re.I), "plan"),
    (re.compile(r"\b(report|snapshot|findings|readout|summary|survey|analysis|takeaways|research|signal)\b", re.I), "report"),
    (re.compile(r"\b(essay|blog)\b", re.I), "essay"),
    (re.compile(r"\bjournal\b", re.I), "journal"),
]

ARTICLE_DEFAULT = "article"

# Tags that say nothing once the subtype carries the same word. Keyed by the
# subtype that was chosen: only a tag that restates *that* subtype is dropped.
# A `feature` tag on a task classified `bug` ("feature X is broken") is still
# information, and stays.
REDUNDANT_TAGS = {
    "bug": {"bug", "bugs"},
    "feature": {"feature"},
    "question": {"open-question", "open-questions", "question"},
    "chore": {"chore"},
    "meeting-notes": {"meeting-notes"},
    "report": {"report"},
    "spec": {"spec"},
    "plan": {"plan"},
    "transcript": {"transcript"},
    "essay": {"essay"},
    "journal": {"journal"},
    "note": {"note", "notes"},
    "article": {"article"},
    "blog-post": {"blog-post"},
    "news": {"news"},
    "book": {"book", "books"},
    "paper": {"paper"},
    "scholarly": {"scholarly"},
    "technical": {"technical"},
    "video": {"video"},
}


@dataclass
class Change:
    path: Path
    node_type: str
    title: str
    subtype: str
    how: str                     # "tag:<tag>", "title", "format", or "default"
    dropped_tags: list[str]

    @property
    def defaulted(self) -> bool:
        return self.how == "default"


def _classify(kind_by_tag, kind_by_title, default, tags: list[str], title: str) -> tuple[str, str]:
    lowered = {str(t).lower() for t in tags}
    for names, subtype in kind_by_tag:
        hit = lowered & names
        if hit:
            return subtype, f"tag:{sorted(hit)[0]}"
    for pattern, subtype in kind_by_title:
        if pattern.search(title or ""):
            return subtype, "title"
    return default, "default"


def plan_node(path: Path, fm: dict) -> Change | None:
    node_type = fm.get("type")
    if node_type not in ("task", "document", "article"):
        return None
    if fm.get("subtype") and "format" not in fm:
        return None

    tags = [str(t) for t in (fm.get("tags") or [])]
    title = str(fm.get("title") or "")

    if node_type == "article":
        if fm.get("subtype"):
            subtype, how = str(fm["subtype"]), "format"
        elif fm.get("format"):
            subtype, how = str(fm["format"]), "format"
        else:
            subtype, how = ARTICLE_DEFAULT, "default"
    elif node_type == "task":
        subtype, how = _classify(TASK_BY_TAG, TASK_BY_TITLE, TASK_DEFAULT, tags, title)
    else:
        subtype, how = _classify(DOCUMENT_BY_TAG, DOCUMENT_BY_TITLE, DOCUMENT_DEFAULT, tags, title)

    dropped = [t for t in tags if t.lower() in REDUNDANT_TAGS.get(subtype, {subtype})]
    return Change(path, node_type, title, subtype, how, dropped)


def apply_change(change: Change, fm: dict, body: str) -> str:
    fm = dict(fm)
    if change.node_type == "article":
        fm.pop("format", None)
    fm["subtype"] = change.subtype
    if change.dropped_tags:
        fm["tags"] = [t for t in (fm.get("tags") or []) if t not in change.dropped_tags]
    # yaml.safe_load turns a bare timestamp into a datetime, which yaml.dump
    # would write back as `2026-01-01 00:00:00+00:00`. Put it back the way
    # every other vault write spells it (see patch_item).
    for key, val in fm.items():
        if isinstance(val, datetime):
            fm[key] = val.strftime("%Y-%m-%dT%H:%M:%SZ")
    # serialize_frontmatter sorts keys, the same way every other vault write does.
    return serialize_frontmatter(fm) + body


def plan_vault(vault_root: Path) -> tuple[list[Change], list[str]]:
    changes: list[Change] = []
    unreadable: list[str] = []
    for path in sorted(vault_root.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        fm_text, _ = split_frontmatter(raw)
        if fm_text is None:
            continue
        try:
            fm = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            unreadable.append(path.name)
            continue
        if not isinstance(fm, dict):
            continue
        change = plan_node(path, fm)
        if change:
            changes.append(change)
    return changes, unreadable


def apply_vault(changes: list[Change]) -> int:
    written = 0
    for change in changes:
        raw = change.path.read_text(encoding="utf-8")
        fm_text, body = split_frontmatter(raw)
        fm = yaml.safe_load(fm_text)
        change.path.write_text(apply_change(change, fm, body), encoding="utf-8")
        written += 1
    return written


def report(changes: list[Change], unreadable: list[str], applied: bool) -> str:
    lines = []
    verb = "Set" if applied else "Would set"
    for c in sorted(changes, key=lambda c: (c.node_type, c.subtype, c.title.lower())):
        drop = f"  (drop tags: {', '.join(c.dropped_tags)})" if c.dropped_tags else ""
        lines.append(f"{verb} {c.node_type:<8} {c.subtype:<14} {c.title}  [{c.how}]{drop}")
    defaulted = [c for c in changes if c.defaulted]
    lines.append("")
    lines.append(f"{len(changes)} node(s) to change; {len(defaulted)} fell through to the default and deserve a look:")
    for c in sorted(defaulted, key=lambda c: (c.node_type, c.title.lower())):
        lines.append(f"  {c.node_type:<8} → {c.subtype:<8} {c.title}")
    if unreadable:
        lines.append("")
        lines.append(f"{len(unreadable)} file(s) skipped — frontmatter did not parse: " + ", ".join(unreadable))
    if not applied:
        lines.append("")
        lines.append("Dry run. Re-run with --apply to write.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("vault_root", type=Path)
    parser.add_argument("--apply", action="store_true", help="write the changes; default is a dry run")
    args = parser.parse_args(argv)

    if not args.vault_root.is_dir():
        print(f"not a directory: {args.vault_root}", file=sys.stderr)
        return 2

    changes, unreadable = plan_vault(args.vault_root)
    if args.apply:
        apply_vault(changes)
    print(report(changes, unreadable, applied=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
