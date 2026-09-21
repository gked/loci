"""
tag_hygiene.py
The rules that keep tags from turning back into the mess they were.

A tag census in September 2026 found 1,103 distinct tags on 567 nodes, 724 of
them used once, and the heaviest ones doing jobs that belong elsewhere: a
project's name (a relation), a kind of thing (a subtype), a subject (a topic).
Two migrations moved those out. This module is what stops them coming back:
the same matching the migrations used, packaged so the linter can warn on a
vault and the writer can warn on a single save.

Nothing here blocks a write. Tags are the loose axis by design; the point is
to say, at the moment a tag is written, "this one has a better home".
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

# Which relation a tag-that-names-a-node should have been.
RELATION_FOR = {"project": "belongs-to", "entity": "involves", "topic": "about"}


# Punctuation that is part of a name rather than a separator: without it
# C, C++ and C# — or R and R&D — would all collapse onto one key.
NAME_SYMBOLS = "+#&"


def normalise(name: str) -> str:
    """Fold case, accents, punctuation and separators so that names which a
    person would read as the same compare equal. Empty when nothing is left."""
    text = unicodedata.normalize("NFKD", str(name)).casefold()
    return "".join(ch for ch in text if ch.isalnum() or ch in NAME_SYMBOLS)


# Words whose final 's' is part of the word, not a plural. A suffix rule came
# first — every `os`/`us`/`is` ending — and it exempted todo/todos, video/videos,
# api/apis, repo/repos: the very plurals a tag vault grows. So the words are
# named instead, along with the pairs that only look like plurals (https is
# not several http; canvas is not several canva). `ss` stays a suffix: css,
# sass, less, class.
KEEPS_ITS_S = frozenset({
    "chaos", "cosmos", "ethos", "status", "bonus", "focus", "virus", "campus",
    "census", "corpus", "analysis", "basis", "thesis", "crisis", "axis", "bias",
    "atlas", "https", "canvas", "news", "lens",
})


def singular_key(name: str) -> str:
    """normalise(), then drop a trailing plural 's' — so `books`/`book` and
    `open-questions`/`open-question` fall into one near-duplicate group."""
    key = normalise(name)
    if len(key) > 3 and key.endswith("s") and not key.endswith("ss") and key not in KEEPS_ITS_S:
        return key[:-1]
    return key


# A parenthetical that is an abbreviation: capitals and digits only, with at
# least one letter, so "(GLX)" and "(2FA)" qualify but "(Acme Corp)",
# "(French startup)" and "(2024)" are glosses and do not.
ABBREVIATION = re.compile(r"^(?=.*[A-Z])[A-Z0-9&.-]+$")


def list_field(fm: dict, key: str) -> list | None:
    """The list under `key`, `[]` when absent or null, `None` when it is
    something else — a bare string iterates as characters, and a dict as
    keys, and neither is what the author meant."""
    val = fm.get(key)
    if val is None:
        return []
    return val if isinstance(val, list) else None


def as_tag_list(val) -> list[str]:
    """Tags as a list whatever shape the frontmatter holds them in. A
    hand-edited `tags: rust` is one tag, not four letters; anything that is
    neither a string nor a list is no tags at all."""
    if val is None:
        return []
    if isinstance(val, str):
        return [val] if val.strip() else []
    if isinstance(val, (list, tuple)):
        # A dangling `-` loads as None; it is a blank line, not a tag "None".
        return [str(t) for t in val if t is not None and str(t).strip()]
    return []


def candidate_names(fm: dict) -> list[str]:
    """The names a node answers to: its title, the title without a trailing
    parenthetical, that parenthetical alone when it is an abbreviation
    ("Globex Corp (GLX)" answers to both, "Initech (company)" does not answer to
    "company"), and its aliases."""
    title = str(fm.get("title") or "")
    names = [title]
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", title)
    if m:
        names.append(m.group(1))
        if ABBREVIATION.match(m.group(2).strip()):
            names.append(m.group(2).strip())
    # A bare string here would be read letter by letter; see list_field.
    names += [str(a) for a in (list_field(fm, "aliases") or [])]
    return [n for n in names if n.strip()]


@dataclass
class Target:
    uid: str
    node_type: str
    title: str


def build_name_index(nodes: Iterable[dict]) -> dict[str, list[Target]]:
    """Map normalised name → the active project/entity/topic nodes that answer
    to it. Each node dict needs uid, type, title, and optionally aliases and
    state — the shape of both a frontmatter dict and a graph node's attrs."""
    index: dict[str, list[Target]] = defaultdict(list)
    for n in nodes:
        if n.get("type") not in RELATION_FOR or n.get("state") == "archived" or not n.get("uid"):
            continue
        target = Target(str(n["uid"]), str(n["type"]), str(n.get("title") or ""))
        seen: set[str] = set()
        for name in candidate_names(n):
            key = normalise(name)
            if key and key not in seen:
                seen.add(key)
                index[key].append(target)
    return index


@dataclass(frozen=True)
class TagWarning:
    code: str        # tag-names-node | tag-repeats-type
    tag: str
    message: str


def check_tags(
    tags,
    node_type: str | None,
    subtype: str | None,
    index: dict[str, list[Target]],
    self_uid: str | None = None,
    relations: Iterable[dict] | None = None,
) -> list[TagWarning]:
    """Warnings for one node's tags: a tag that repeats the node's own type or
    subtype (`books` on a book counts — the plural rule says they are one
    word), and a tag that names a project/entity/topic (ambiguous names —
    two nodes answering to one — are left alone, as the migration leaves
    them). When the node already links to that target the tag is simply
    redundant — say so, rather than ask for an edge that exists."""
    own = {singular_key(node_type or ""), singular_key(subtype or "")} - {""}
    linked = {str(r.get("uid")) for r in (relations or []) if isinstance(r, dict) and r.get("uid")}
    out: list[TagWarning] = []
    for tag in as_tag_list(tags):
        key = normalise(tag)
        if not key:
            continue
        if singular_key(tag) in own:
            out.append(TagWarning(
                "tag-repeats-type", tag,
                f"tag '{tag}' repeats the node's own type/subtype — the field already says it; drop the tag",
            ))
            continue
        targets = [t for t in index.get(key, []) if t.uid != self_uid]
        if len({t.uid for t in targets}) == 1:
            t = targets[0]
            if t.uid in linked:
                msg = f"tag '{tag}' names {t.node_type} '{t.title}' ({t.uid}), which this node already links to — drop the tag"
            else:
                msg = f"tag '{tag}' names {t.node_type} '{t.title}' ({t.uid}) — use a {RELATION_FOR[t.node_type]} relation instead"
            out.append(TagWarning("tag-names-node", tag, msg))
    return out


def near_duplicate_groups(tag_counts: Counter) -> list[list[str]]:
    """Groups of tags that differ only by case, separators, accents, or a
    plural 's' — `acme-corp`/`acmecorp`, `open-question`/`open-questions`.
    Most-used spelling first within each group, the lowercase one on a tie —
    a `Chore`/`chore` split is resolved toward the convention, not the
    capital; groups by size."""
    groups: dict[str, list[str]] = defaultdict(list)
    for tag in tag_counts:
        key = singular_key(tag)
        if key:
            groups[key].append(tag)
    result = [sorted(g, key=lambda t: (-tag_counts[t], t != t.casefold(), t))
              for g in groups.values() if len(g) > 1]
    return sorted(result, key=lambda g: (-sum(tag_counts[t] for t in g), g[0]))


def singletons(tag_counts: Counter) -> list[str]:
    """Tags used exactly once, most recent-looking last (alphabetical)."""
    return sorted(t for t, n in tag_counts.items() if n == 1)
