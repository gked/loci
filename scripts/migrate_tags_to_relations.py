"""
scripts/migrate_tags_to_relations.py
Turn tags that name a node into edges to that node.

A project's name as a tag on fifty notes is fifty strings the graph cannot
see, where one `belongs-to` edge each would do. The tag census that led to
subtypes (task 8e50477e) found that the heaviest tags in the vault are
exactly this: `loci`, `mercury`, `acme-corp`, `user-research` — every one
the title of a project, entity, or topic node. This script converts them:

  * tag names a **project** → `belongs-to` that project
  * tag names an **entity**  → `involves` that entity
  * tag names a **topic**    → `about` that topic

and drops the tag, since the edge now carries what the tag said. A tag whose
target the node is already linked to (by any relation) is dropped without
adding a second edge. A node is never linked to itself.

A tag that merely repeats the node's own `type` or `subtype` (`#book` on an
asset whose subtype is book, `#skill` on a skill) is dropped too — the field
already says it, and the query that used to need the tag now filters on the
field.

Matching is on normalised names — case, punctuation, and separators are
ignored, so `acme-corp` and `acmecorp` both find "Acme Corp", though `+`,
`#` and `&` are kept so that C, C++ and C# stay three names — against each
candidate node's title, the title without a trailing parenthetical, the
parenthetical when it is an abbreviation ("Globex Corp (GLX)" answers to both;
"Initech (French startup)" only to Initech), and its aliases.
Only active project, entity, and topic nodes are candidates. A name shared by
two candidate nodes is ambiguous and left alone, reported for you to resolve.

Nothing is written unless `--apply` is given. The dry run prints the plan,
the ambiguous names, and the most-used tags that match no node at all — those
are where a topic node or an alias is probably missing. Both are counted by
normalised name, so `Python` and `python` are one tag, shown with every
spelling seen.

A node whose `tags` is not a list is skipped and reported rather than
guessed at — iterating a bare string would read it letter by letter. A
non-list `aliases` is ignored the same way.

Usage:
    uv run python scripts/migrate_tags_to_relations.py <vault-root>            # plan only
    uv run python scripts/migrate_tags_to_relations.py <vault-root> --apply    # write
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from loci.tools.frontmatter import split_frontmatter
from loci.tools.write_file import serialize_frontmatter

RELATION_FOR = {"project": "belongs-to", "entity": "involves", "topic": "about"}

# Tags below this many uses are not worth reporting as "no node found".
UNMATCHED_REPORT_MIN = 3


# Punctuation that is part of a name rather than a separator: without it
# C, C++ and C# — or R and R&D — would all collapse onto one key.
NAME_SYMBOLS = "+#&"


def normalise(name: str) -> str:
    """Fold case, accents, punctuation and separators so that names which a
    person would read as the same compare equal. Empty when nothing is left."""
    text = unicodedata.normalize("NFKD", str(name)).casefold()
    return "".join(ch for ch in text if ch.isalnum() or ch in NAME_SYMBOLS)


# A parenthetical that is an abbreviation: capitals and digits only, with at
# least one letter, so "(GLX)" and "(2FA)" qualify but "(Acme Corp)",
# "(French startup)" and "(2024)" are glosses and do not.
ABBREVIATION = re.compile(r"^(?=.*[A-Z])[A-Z0-9&.-]+$")


def candidate_names(fm: dict) -> list[str]:
    title = str(fm.get("title") or "")
    names = [title]
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", title)
    if m:
        names.append(m.group(1))
        # "(GLX)" is a name; "(company)" is a gloss. Only an abbreviation
        # is worth answering to.
        if ABBREVIATION.match(m.group(2).strip()):
            names.append(m.group(2).strip())
    # A bare string here would be read letter by letter; see list_field.
    names += [str(a) for a in (list_field(fm, "aliases") or [])]
    return [n for n in names if n.strip()]


def list_field(fm: dict, key: str) -> list | None:
    """The list under `key`, `[]` when absent or null, `None` when it is
    something else — a bare string iterates as characters, and a dict as
    keys, and neither is what the author meant."""
    val = fm.get(key)
    if val is None:
        return []
    return val if isinstance(val, list) else None


@dataclass
class Target:
    uid: str
    node_type: str
    title: str


@dataclass
class Edge:
    path: Path
    uid: str
    title: str
    tag: str
    target: Target | None       # None when the tag repeats the node's own type/subtype
    relation: str
    already_linked: bool

    @property
    def drop_only(self) -> bool:
        return self.already_linked or self.target is None


@dataclass
class Plan:
    edges: list[Edge] = field(default_factory=list)
    ambiguous: dict[str, list[Target]] = field(default_factory=dict)   # normalised tag → the nodes it could mean
    unmatched: Counter = field(default_factory=Counter)                # normalised tag → uses, no node found
    spellings: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))  # normalised tag → tags as written
    problems: list[str] = field(default_factory=list)                  # files whose frontmatter could not be used as-is

    @property
    def to_add(self) -> list[Edge]:
        return [e for e in self.edges if not e.drop_only]

    def label(self, key: str) -> str:
        """A normalised tag as it is most often written, with any other
        spellings after it: `python`, or `Python [also python]`."""
        seen = self.spellings[key].most_common()
        head = seen[0][0] if seen else key
        also = ", ".join(s for s, _ in seen[1:])
        return f"#{head}" + (f" [also {also}]" if also else "")


def load_vault(vault_root: Path) -> tuple[dict[Path, dict], list[str]]:
    nodes: dict[Path, dict] = {}
    problems: list[str] = []
    for path in sorted(vault_root.glob("*.md")):
        fm_text, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        if fm_text is None:
            continue
        try:
            fm = yaml.safe_load(fm_text)
        except yaml.YAMLError:
            problems.append(f"{path.name}: frontmatter did not parse — skipped")
            continue
        if not (isinstance(fm, dict) and fm.get("uid")):
            continue
        if list_field(fm, "aliases") is None:
            problems.append(f"{path.name}: aliases is not a list — ignored")
        nodes[path] = fm
    return nodes, problems


def index_targets(nodes: dict[Path, dict]) -> dict[str, list[Target]]:
    index: dict[str, list[Target]] = defaultdict(list)
    for fm in nodes.values():
        if fm.get("type") not in RELATION_FOR or fm.get("state") == "archived":
            continue
        target = Target(str(fm["uid"]), str(fm["type"]), str(fm.get("title") or ""))
        seen: set[str] = set()
        for name in candidate_names(fm):
            key = normalise(name)
            if key and key not in seen:
                seen.add(key)
                index[key].append(target)
    return index


def plan_vault(vault_root: Path) -> Plan:
    nodes, problems = load_vault(vault_root)
    targets = index_targets(nodes)
    plan = Plan(problems=problems)

    for path, fm in nodes.items():
        uid = str(fm["uid"])
        tags = list_field(fm, "tags")
        if tags is None:
            plan.problems.append(f"{path.name}: tags is not a list — skipped")
            continue
        linked = {str(r.get("uid")) for r in (fm.get("relations") or []) if isinstance(r, dict)}
        own = {normalise(fm.get("type") or ""), normalise(fm.get("subtype") or "")} - {""}
        for tag in tags:
            tag = str(tag)
            key = normalise(tag)
            if key in own:
                plan.edges.append(Edge(path, uid, str(fm.get("title") or ""), tag, None, "", already_linked=True))
                continue
            candidates = targets.get(key) if key else None
            if not candidates:
                plan.unmatched[key] += 1
                plan.spellings[key][tag] += 1
                continue
            distinct = {c.uid: c for c in candidates}
            if len(distinct) > 1:
                plan.ambiguous.setdefault(key, list(distinct.values()))
                plan.spellings[key][tag] += 1
                continue
            target = candidates[0]
            # A node tagged with its own name has nothing to link to; the tag
            # still goes, as it says nothing the title does not.
            self_tag = target.uid == uid
            plan.edges.append(Edge(
                path, uid, str(fm.get("title") or ""), tag, target,
                RELATION_FOR[target.node_type], already_linked=self_tag or target.uid in linked,
            ))
            # Two tags for one node (`acme-corp`, `acmecorp`) plan one edge.
            linked.add(target.uid)
    return plan


def apply_plan(plan: Plan) -> int:
    by_path: dict[Path, list[Edge]] = defaultdict(list)
    for e in plan.edges:
        by_path[e.path].append(e)

    written = 0
    for path, edges in by_path.items():
        raw = path.read_text(encoding="utf-8")
        fm_text, body = split_frontmatter(raw)
        fm = yaml.safe_load(fm_text)
        relations = list(fm.get("relations") or [])
        drop = {e.tag for e in edges}
        for e in edges:
            if e.drop_only:
                continue
            relations.append({"uid": e.target.uid, "type": e.relation})
        fm["relations"] = relations
        fm["tags"] = [t for t in (fm.get("tags") or []) if str(t) not in drop]
        # yaml.safe_load turns a bare timestamp into a datetime, which would
        # serialise as `2026-01-01 00:00:00+00:00`. Spell it the way every
        # other vault write does (see patch_item), and join the body the same
        # way too — split_frontmatter keeps the fence's newline on the body.
        for key, val in fm.items():
            if isinstance(val, datetime):
                fm[key] = val.strftime("%Y-%m-%dT%H:%M:%SZ")
        path.write_text(serialize_frontmatter(fm) + "\n" + body.lstrip("\n"), encoding="utf-8")
        written += 1
    return written


def report(plan: Plan, applied: bool) -> str:
    verb_add, verb_drop = ("Added", "Dropped") if applied else ("Add", "Drop")
    lines: list[str] = []

    per_target: dict[str, list[Edge]] = defaultdict(list)
    for e in plan.edges:
        if e.target is not None:
            per_target[e.target.uid].append(e)
    for uid, edges in sorted(per_target.items(), key=lambda kv: -len(kv[1])):
        t = edges[0].target
        adds = [e for e in edges if not e.drop_only]
        tags = sorted({e.tag for e in edges})
        lines.append(
            f"[{t.node_type}] {t.title} ({t.uid}): {verb_add} {len(adds)} "
            f"{RELATION_FOR[t.node_type]} edge(s); {verb_drop} tag(s) {', '.join('#' + x for x in tags)} "
            f"from {len({e.path for e in edges})} node(s)"
        )

    own = Counter(e.tag for e in plan.edges if e.target is None)
    if own:
        lines.append("")
        lines.append(f"Tags that repeat the node's own type or subtype — {verb_drop.lower()} only:")
        lines.append("  " + ", ".join(f"#{tag}({n})" for tag, n in own.most_common()))

    lines.append("")
    lines.append(
        f"{len(plan.to_add)} edge(s) to add, {len(plan.edges)} tag use(s) to drop, "
        f"across {len({e.path for e in plan.edges})} node(s)."
    )

    if plan.ambiguous:
        lines.append("")
        lines.append("Ambiguous — a tag that could mean more than one node; left alone:")
        for key, targets in plan.ambiguous.items():
            lines.append(f"  {plan.label(key)} → " + " | ".join(f"[{t.node_type}] {t.title} ({t.uid})" for t in targets))

    heavy = [(key, n) for key, n in plan.unmatched.most_common() if n >= UNMATCHED_REPORT_MIN]
    if heavy:
        lines.append("")
        lines.append(f"Tags used {UNMATCHED_REPORT_MIN}+ times that match no project, entity, or topic — a missing node or alias?")
        lines.append("  " + ", ".join(f"{plan.label(key)}({n})" for key, n in heavy[:40]))

    if plan.problems:
        lines.append("")
        lines.append(f"{len(plan.problems)} file(s) with frontmatter that could not be used as written:")
        lines.extend(f"  {p}" for p in plan.problems)
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

    plan = plan_vault(args.vault_root)
    if args.apply:
        apply_plan(plan)
    print(report(plan, applied=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
