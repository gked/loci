#!/usr/bin/env python3
"""
Generate a scale vault for `make dev`.

`make dev` serves `dev-vault/`, which starts empty, so the UI comes up blank
and reads as broken. The fixture vault would fill the screen, but at 31 nodes
it is far below the ~500 a real vault carries — and that gap is where graph
layout, the tag rail, index scrolling and palette ranking actually strain.

The output is committed as `dev-vault-seed/` and copied into `dev-vault/` when
`make dev` first creates it. This script exists so a regeneration after an
ontology change is a command rather than a rewrite; it is not wired into the
Makefile and the seed is what ships.

    uv run python scripts/dev_seed.py --out dev-vault-seed --n 500 --seed 1

Types, subtypes, enum values and relation names are drawn from the registries,
so the output cannot encode a snapshot of the ontology that silently rots.
Everything is derived from `--seed`, so the same seed gives byte-identical
output. A `--ghosts` count adds that many relations to uids no node carries —
the ghost state the UI special-cases — and each one is a `dangling-relation`
lint warning; the seed carries one, and the test asserts it is the only one.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

from loci.tools.relation_registry import get_relation_registry  # noqa: E402
from loci.tools.vault_init import load_config  # noqa: E402
from loci.tools.slug import filename as make_filename  # noqa: E402
from loci.tools.type_registry import TypeDef, get_registry  # noqa: E402
from loci.tools.write_file import serialize_frontmatter  # noqa: E402

# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------

# Weighted like a real vault: captured content dominates, structure is sparse.
TYPE_WEIGHTS = {
    "document": 18,
    "article": 16,
    "bookmark": 14,
    "task": 12,
    "topic": 6,
    "conversation": 6,
    "entity": 8,
    "project": 4,
    "event": 4,
    "procedure": 4,
    "asset": 5,
    "log": 3,
}

# Types that act as hubs: they draw the bulk of the edges.
HUB_TYPES = {"topic", "project", "entity"}
HUB_FRACTION = 0.05

DOMAINS = [
    "technology-engineering", "science-research", "business-strategy",
    "finance-economics", "health-biology", "philosophy-ethics",
    "creativity-design", "personal-development", "current-events-society",
]

# Relation chosen by (source type, target type); anything unlisted falls back
# to relates-to. Every name is checked against the relation registry.
RELATION_BY_PAIR = {
    ("task", "project"): "belongs-to",
    ("task", "task"): "depends-on",
    ("event", "project"): "belongs-to",
    ("document", "project"): "belongs-to",
    ("document", "topic"): "about",
    ("article", "topic"): "about",
    ("bookmark", "topic"): "about",
    ("conversation", "topic"): "about",
    ("topic", "topic"): "is-part-of",
    ("project", "topic"): "about",
    ("procedure", "project"): "used-in",
    ("procedure", "topic"): "about",
    ("log", "asset"): "about",
    ("asset", "topic"): "about",
    ("article", "entity"): "mentions",
    ("document", "entity"): "mentions",
    ("conversation", "entity"): "involves",
    ("event", "entity"): "involves",
}

# Entity pairs are keyed on subtype: works-at is defined as person -> organisation,
# and any other entity pair (person -> person, place -> place) is just related.
RELATION_BY_SUBTYPE_PAIR = {
    ("person", "organization"): "works-at",
}

# The second of each pair is derived from the first, so an event never ends
# before it starts and a log never finishes before it started.
PAIRED_DATETIMES = {"end_at": "start_at", "finished_at": "started_at"}

ADJECTIVES = [
    "quiet", "brittle", "layered", "durable", "sparse", "recursive", "borrowed",
    "late", "narrow", "plain", "restless", "stable", "hidden", "adaptive",
    "minimal", "slow", "practical", "ambient", "local", "portable",
]
NOUNS = [
    "index", "ledger", "garden", "protocol", "cache", "harbour", "lattice",
    "draft", "compass", "signal", "ledger", "threshold", "archive", "loop",
    "margin", "field", "orbit", "handle", "kernel", "season", "corridor",
    "pattern", "budget", "workshop", "outline", "register", "meridian",
]
VERBS = [
    "migrate", "review", "sketch", "refactor", "measure", "archive", "draft",
    "compare", "rebuild", "document", "trace", "prune", "audit", "prototype",
]
TAG_POOL = [
    "loci", "design", "notes", "reading", "python", "react", "graph", "writing",
    "research", "meeting", "idea", "reference", "howto", "review", "planning",
    "ontology", "tooling", "cli", "ux", "performance", "testing", "release",
    "infra", "docker", "mcp", "vault", "search", "typography", "journal",
    "health", "finance", "book", "paper", "talk", "podcast", "history",
    "philosophy", "economics", "biology", "hardware", "networking", "security",
    "data", "statistics", "learning", "language", "music", "travel", "cooking",
    "gardening", "woodwork", "climbing", "running", "sleep", "habits",
    "productivity", "email", "calendar", "backup", "migration",
]
# Entity titles are drawn without replacement: a vault does not carry two
# person nodes of one name, and api.save refuses an exact title match, so a
# duplicate in the seed makes that name unsaveable in the dev vault.
PEOPLE = [
    "Mara Lindqvist", "Tomas Reyes", "Anouk de Vries", "Kenji Okabe",
    "Priya Raman", "Olu Adeyemi", "Sofia Marchetti", "Daniel Brenner",
    "Ines Carvalho", "Yusuf Demir", "Hanna Sorensen", "Leo Fontaine",
    "Nadia Haddad", "Elias Wolf", "Ruth Okonkwo", "Mateo Salinas",
    "Freya Nilsen", "Arjun Mehta", "Clara Voss", "Samuel Achebe",
    "Yara Khalil", "Bruno Ferreira", "Aiko Tanaka", "Piotr Nowak",
    "Zainab Rashid", "Henrik Dahl", "Lucia Romano", "Owen Gallagher",
    "Sun-hee Park", "Ibrahim Sow",
]
ORGS = [
    "Northwind Labs", "Halden Institute", "Cobalt Systems", "Meridian Press",
    "Ferrous Works", "Larkspur Collective", "Tidewater Analytics",
    "Basalt Foundry", "Quill and Compass", "Orchard Street Studio",
    "Greywater Research", "Saltmarsh Cooperative", "Pinewood Archive",
    "Harbourline Software", "Aster Field Guides", "Lantern Row Books",
    "Cinder Hill Observatory", "Fathom Instruments", "Wren and Kite",
    "Slate Ridge Partners",
]
PLACES = [
    "Lisbon", "Tallinn", "Kyoto", "Bergen", "Montreal", "Valparaiso", "Tbilisi",
    "Porto", "Ljubljana", "Sapporo", "Tromso", "Halifax", "Cusco", "Batumi",
    "Ghent", "Turku", "Naoshima", "Reykjavik", "Quebec City", "Salta",
]
SITES = [
    "example.org", "notes.example.com", "blog.example.net", "papers.example.edu",
    "docs.example.io", "journal.example.co",
]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class Generator:
    def __init__(self, n: int, seed: int, ghosts: int):
        self.n = n
        self.rng = random.Random(seed)
        self.ghosts = ghosts
        self.types = get_registry(None)
        self.relations = get_relation_registry(None)
        self.epoch = datetime(2025, 3, 1, tzinfo=timezone.utc)
        self.span_days = 540
        self.nodes: list[dict] = []
        self.uids: set[str] = set()
        self.filenames: set[str] = set()
        self.entity_titles: set[str] = set()
        self._check_vocab()

    def _check_vocab(self) -> None:
        unknown_types = set(TYPE_WEIGHTS) - self.types.type_names()
        if unknown_types:
            raise SystemExit(f"TYPE_WEIGHTS names types not in the ontology: {sorted(unknown_types)}")
        named = list(RELATION_BY_PAIR.values()) + list(RELATION_BY_SUBTYPE_PAIR.values())
        unknown_rels = {r for r in named if not self.relations.is_valid(r)}
        if unknown_rels:
            raise SystemExit(f"RELATION_BY_*_PAIR names relations not in the dictionary: {sorted(unknown_rels)}")

    # -- primitives -----------------------------------------------------------

    def uid(self) -> str:
        while True:
            uid = "%08x" % self.rng.getrandbits(32)
            if uid not in self.uids:
                self.uids.add(uid)
                return uid

    def when(self, offset_days: float | None = None) -> datetime:
        if offset_days is None:
            offset_days = self.rng.uniform(0, self.span_days)
        seconds = self.rng.randrange(0, 86400)
        return self.epoch + timedelta(days=offset_days, seconds=seconds)

    @staticmethod
    def stamp(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def phrase(self) -> str:
        return f"{self.rng.choice(ADJECTIVES)} {self.rng.choice(NOUNS)}"

    def sentence(self) -> str:
        return (
            f"The {self.phrase()} {self.rng.choice(VERBS)}s the "
            f"{self.phrase()} before the {self.rng.choice(NOUNS)} settles."
        ).capitalize()

    def paragraph(self) -> str:
        return " ".join(self.sentence() for _ in range(self.rng.randint(2, 5)))

    def tags(self) -> list[str]:
        # Zipf-ish: the head of TAG_POOL is far more likely than the tail.
        weights = [1.0 / (i + 1) for i in range(len(TAG_POOL))]
        picked: list[str] = []
        for tag in self.rng.choices(TAG_POOL, weights=weights, k=self.rng.randint(3, 6)):
            if tag not in picked:
                picked.append(tag)
        return picked

    def enum_value(self, values: list[str]) -> str:
        return self.rng.choice(values)

    # -- per-type fields --------------------------------------------------

    def entity_title(self, pool: list[str]) -> str:
        unused = [name for name in pool if name not in self.entity_titles]
        if unused:
            title = self.rng.choice(unused)
        else:
            # Pool dry (a --n well past 500): recombine first and last words so
            # the vault still holds no two entities of one name.
            for attempt in range(1000):
                a, b = self.rng.sample(pool, 2)
                title = f"{a.split()[0]} {b.split()[-1]}"
                if title not in self.entity_titles:
                    break
            else:
                raise SystemExit(f"entity name pool exhausted at {len(self.entity_titles)} names; widen the pools")
        self.entity_titles.add(title)
        return title

    def title_for(self, ntype: str, subtype: str | None) -> str:
        if ntype == "entity":
            if subtype == "person":
                return self.entity_title(PEOPLE)
            if subtype == "organization":
                return self.entity_title(ORGS)
            return self.entity_title(PLACES)
        if ntype == "task":
            return f"{self.rng.choice(VERBS).capitalize()} the {self.phrase()}"
        if ntype == "project":
            return f"{self.phrase().title()} project"
        if ntype == "topic":
            return self.phrase().title()
        if ntype == "event":
            return f"{self.phrase().title()} meeting"
        if ntype == "procedure":
            return f"How to {self.rng.choice(VERBS)} a {self.phrase()}"
        if ntype == "conversation":
            return f"On the {self.phrase()}"
        if ntype == "log":
            return f"Reading log: {self.phrase()}"
        return f"{self.phrase().title()}: {self.rng.choice(NOUNS)} and {self.rng.choice(NOUNS)}"

    def field_value(self, name: str, ftype: str, values: list[str] | None, ntype: str, created: datetime):
        if ftype == "enum" and values:
            return self.enum_value(values)
        if ftype == "datetime":
            return self.stamp(self.when(min(self.span_days, (created - self.epoch).days + self.rng.uniform(1, 60))))
        if ftype == "array":
            if name == "participants":
                return self.rng.sample(PEOPLE, self.rng.randint(1, 3))
            if name == "steps":
                return [self.sentence() for _ in range(self.rng.randint(3, 7))]
            return [self.phrase() for _ in range(self.rng.randint(1, 3))]
        if ftype == "boolean":
            return self.rng.random() < 0.5
        # string
        if name == "source_url":
            return f"https://{self.rng.choice(SITES)}/{self.rng.choice(NOUNS)}/{self.rng.randrange(1000, 9999)}"
        if name == "site_name":
            return self.rng.choice(SITES)
        if name == "author":
            return self.rng.choice(PEOPLE)
        if name == "assignee":
            return self.rng.choice(PEOPLE)
        if name == "location":
            return self.rng.choice(PLACES)
        if name == "organization":
            return self.rng.choice(ORGS)
        if name == "website":
            return f"https://{self.rng.choice(SITES)}"
        if name == "model":
            return "claude-opus-5"
        if name == "turns":
            return str(self.rng.randint(2, 40))
        if name == "duration_minutes":
            return str(self.rng.choice([5, 10, 15, 30, 45, 60, 90]))
        if name == "rating":
            return str(self.rng.randint(1, 5))
        if name == "industry":
            return self.rng.choice(NOUNS)
        return self.phrase()

    def extra_fields(self, tdef: TypeDef, subtype: str | None, created: datetime) -> dict:
        fields: dict = {}
        for f in tdef.required_fields:
            if f.name == "subtype":
                fields[f.name] = subtype
            elif f.name == "subject_uid":
                fields[f.name] = None  # patched once every node has a uid
            else:
                fields[f.name] = self.field_value(f.name, f.type, f.values, tdef.name, created)
        for f in tdef.optional_fields:
            if self.rng.random() < 0.5:
                fields[f.name] = self.field_value(f.name, f.type, f.values, tdef.name, created)
        if subtype and subtype in tdef.subtype_fields:
            for f in tdef.subtype_fields[subtype]:
                if self.rng.random() < 0.7:
                    fields[f.name] = self.field_value(f.name, f.type, f.values, tdef.name, created)
        for later, earlier in PAIRED_DATETIMES.items():
            if later in fields and earlier in fields:
                start = datetime.strptime(fields[earlier], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                fields[later] = self.stamp(start + timedelta(hours=self.rng.uniform(0.5, 72)))
        return fields

    # -- nodes ---------------------------------------------------------------

    def make_node(self, ntype: str, hub: bool) -> dict:
        tdef = self.types.get(ntype)
        subtype = None
        for f in tdef.required_fields:
            if f.name == "subtype" and f.values:
                subtype = self.enum_value(f.values)

        # Later stamps are capped at the span end, as field_value caps every
        # other datetime — otherwise the seed carries dates in the future and
        # the UI's recent views lead with them.
        end = self.epoch + timedelta(days=self.span_days)
        created = self.when()
        updated = min(end, created + timedelta(days=self.rng.uniform(0, 90))) if self.rng.random() < 0.6 else created
        archived = not hub and self.rng.random() < 0.05
        archived_at = min(end, updated + timedelta(days=self.rng.uniform(1, 30))) if archived else None

        title = self.title_for(ntype, subtype)
        fm = {
            "uid": self.uid(),
            "type": ntype,
            "title": title,
            "author": "self",
            "state": "archived" if archived else "active",
            "created_at": self.stamp(created),
            "updated_at": self.stamp(updated),
            "archived_at": self.stamp(archived_at) if archived_at else None,
            "tags": self.tags(),
            "domains": self.rng.sample(DOMAINS, self.rng.choice([1, 1, 1, 2])),
            "summary": self.sentence() + " " + self.sentence(),
            "relations": [],
            "references": [],
        }
        fm.update(self.extra_fields(tdef, subtype, created))
        if ntype in ("article", "bookmark") and self.rng.random() < 0.3:
            fm["references"] = [{"url": fm["source_url"], "title": title, "source_type": "web"}]

        body = f"## {title}\n\n" + "\n\n".join(self.paragraph() for _ in range(self.rng.randint(1, 4))) + "\n"
        return {"fm": fm, "body": body, "hub": hub}

    def filename_for(self, title: str) -> str:
        fname = make_filename(title)
        stem, ext = fname.rsplit(".", 1)
        n = 2
        while fname in self.filenames:
            fname = f"{stem}-{n}.{ext}"
            n += 1
        self.filenames.add(fname)
        return fname

    # -- graph -----------------------------------------------------------------

    def relation_name(self, src: dict, dst: dict) -> str:
        src_type, dst_type = src["fm"]["type"], dst["fm"]["type"]
        if src_type == dst_type == "entity":
            return RELATION_BY_SUBTYPE_PAIR.get((src["fm"]["subtype"], dst["fm"]["subtype"]), "relates-to")
        return RELATION_BY_PAIR.get((src_type, dst_type), "relates-to")

    def link(self, src: dict, dst: dict) -> None:
        if src is dst:
            return
        if any(r["uid"] == dst["fm"]["uid"] for r in src["fm"]["relations"]):
            return
        src["fm"]["relations"].append({
            "type": self.relation_name(src, dst),
            "uid": dst["fm"]["uid"],
        })

    def wire(self) -> None:
        hubs = [n for n in self.nodes if n["hub"]]
        others = [n for n in self.nodes if not n["hub"]]

        # Preferential attachment: a hub's weight grows with its in-degree, so a
        # few hubs end up carrying most of the edges.
        indegree = {id(h): 1 for h in hubs}
        for node in others:
            for _ in range(self.rng.choice([1, 1, 2, 2, 3])):
                if hubs and self.rng.random() < 0.8:
                    target = self.rng.choices(hubs, weights=[indegree[id(h)] for h in hubs])[0]
                    indegree[id(target)] += 1
                else:
                    target = self.rng.choice(self.nodes)
                self.link(node, target)

        # Hubs link among themselves so none is left orphaned.
        for hub in hubs:
            self.link(hub, self.rng.choice(hubs))
            if not hub["fm"]["relations"]:
                self.link(hub, self.rng.choice(others))

        # Logs point at what they record.
        assets = [n for n in self.nodes if n["fm"]["type"] == "asset"]
        for node in self.nodes:
            if node["fm"]["type"] == "log":
                candidates = assets or [n for n in others if n is not node]
                subject = self.rng.choice(candidates)
                node["fm"]["subject_uid"] = subject["fm"]["uid"]
                self.link(node, subject)

        for _ in range(self.ghosts):
            ghost = "%08x" % self.rng.getrandbits(32)
            while ghost in self.uids:
                ghost = "%08x" % self.rng.getrandbits(32)
            self.uids.add(ghost)  # never reused as a real uid later
            src = self.rng.choice(others)
            src["fm"]["relations"].append({"type": "relates-to", "uid": ghost})

    # -- driver ----------------------------------------------------------------

    def build(self) -> list[tuple[str, str]]:
        names = list(TYPE_WEIGHTS)
        weights = [TYPE_WEIGHTS[t] for t in names]
        hub_count = max(1, int(self.n * HUB_FRACTION))
        hub_types = [t for t in names if t in HUB_TYPES]
        for _ in range(hub_count):
            self.nodes.append(self.make_node(self.rng.choice(hub_types), hub=True))
        for ntype in self.rng.choices(names, weights=weights, k=self.n - hub_count):
            self.nodes.append(self.make_node(ntype, hub=False))
        self.wire()

        out = []
        for node in self.nodes:
            fname = self.filename_for(node["fm"]["title"])
            out.append((fname, serialize_frontmatter(node["fm"]) + "\n" + node["body"]))
        return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _is_within(path: Path, root: Path) -> bool:
    root = root.resolve()
    return path == root or root in path.parents


def check_target(out: Path, force: bool) -> None:
    """
    Two directories are refused outright, --force or not: the fixtures, whose
    composition the suites assert on, and the vault Loci is configured to use
    — --force unlinks every .md in the target, and the user's notes are not
    in git.
    """
    resolved = out.resolve()
    if _is_within(resolved, FIXTURES_DIR):
        raise SystemExit(
            f"refusing to write into {FIXTURES_DIR}: its composition is asserted "
            "on by the test suites"
        )
    config = load_config() or {}
    vault_root = config.get("vault_root")
    if vault_root and _is_within(resolved, Path(vault_root).expanduser()):
        raise SystemExit(
            f"refusing to write into {vault_root}: it is the configured Loci vault "
            "(LOCI_VAULT_ROOT or vault_root in the config file), not a dev scratch directory"
        )
    if resolved.is_file():
        raise SystemExit(f"{out} is a file, not a directory")
    if resolved.exists() and any(resolved.iterdir()) and not force:
        raise SystemExit(f"{out} is not empty; pass --force to replace its .md files")


def write(out: Path, files: list[tuple[str, str]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.md"):
        stale.unlink()
    for fname, content in files:
        (out / fname).write_text(content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="directory to write the vault into")
    parser.add_argument("--n", type=int, default=500, help="number of nodes (default 500)")
    parser.add_argument("--seed", type=int, default=1, help="RNG seed (default 1)")
    parser.add_argument("--ghosts", type=int, default=1, help="dangling relations to plant (default 1)")
    parser.add_argument("--force", action="store_true", help="replace the .md files of a non-empty target")
    args = parser.parse_args(argv)
    if args.n < 2:
        parser.error("--n must be at least 2: one node is a hub with nothing to link to")

    check_target(args.out, args.force)
    files = Generator(args.n, args.seed, args.ghosts).build()
    write(args.out, files)
    print(f"wrote {len(files)} nodes to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
