"""
node_merge.py
Resolves "(conflicted copy …)" node files that a sync tool leaves behind when the
same node was edited on two computers.

The kept file is version A (`foo.md`). The copy is version B
(`foo (conflicted copy 2026-11-14 081923).md`). The common ancestor comes from the
vault history: the file as it was where the two computers' branches forked.

Edits to different lines merge on their own. Edits to the same lines are left to
the user, one choice per clash. Nothing is written until `resolve` runs, and
`resolve` computes the merge again from the files on disk. A caller that passes
the `token` from `describe` is refused when the clashes have changed since.

Four cases, from `describe`:
  merged    both sides merge with no clash
  conflict  at least one clash; the user picks a side for each
  restore   the original is gone (deleted on the other computer) and the copy
            holds an edit: the edit wins and the copy takes the original name
  keep-both two different nodes took one file name; the copy gets a free name
"""

import difflib
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loci.tools import vault_history
from loci.tools.frontmatter import load_frontmatter, split_frontmatter

# "foo (conflicted copy 2026-11-14 081923).md", also with a user name in the
# brackets ("foo (Max's conflicted copy 2026-11-14).md"). Only notes: the vault
# keeps no other files in its history.
COPY_RE = re.compile(r"^(?P<stem>.+?) \([^()]*conflicted copy[^()]*\)\.md$", re.IGNORECASE)

_UPDATED_AT = re.compile(r"(?m)^updated_at:.*$")


class MergeError(Exception):
    """A conflicted copy cannot be handled: unknown name, unreadable file, bad choice."""


def is_conflicted_copy(path: Path | str) -> bool:
    """True when the file name is a sync tool's conflicted copy of a note. Such a
    file shares its uid with the note it came from and is not a node."""
    return bool(COPY_RE.match(Path(path).name))


def conflicted_copies(vault_root: Path) -> list[Path]:
    """Every conflicted-copy note in the vault root, sorted by name."""
    return sorted(p for p in Path(vault_root).glob("*.md") if COPY_RE.match(p.name) and p.is_file())


def original_name(copy_name: str) -> str:
    match = COPY_RE.match(copy_name)
    if not match:
        raise MergeError(f"{copy_name!r} is not a conflicted copy.")
    return match.group("stem") + ".md"


# ---------------------------------------------------------------------------
# Three-way merge
# ---------------------------------------------------------------------------

@dataclass
class Clash:
    """Lines both sides changed in different ways."""
    base: list[str]
    a: list[str]
    b: list[str]


def _lines(text: str) -> list[str]:
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += "\n"   # a missing final newline on one side is not an edit
    return lines


def _end_like(segments: list, kept: str) -> list:
    """The merge works on whole lines, so its text always ends with a newline.
    Give it the kept file's ending: no final newline there, none in the result."""
    if kept.endswith(("\n", "\r")) or not segments or not isinstance(segments[-1], str):
        return segments
    last = segments[-1]
    segments[-1] = last[:-2] if last.endswith("\r\n") else last[:-1]
    return segments


def _matches(base: list[str], other: list[str]) -> dict[int, int]:
    """base line index -> other line index, for the lines both share."""
    found: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(None, base, other, autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            found[block.a + k] = block.b + k
    return found


def merge3(base: str, a: str, b: str) -> list:
    """Merge `a` and `b`, which both derive from `base`. Returns segments in file
    order: a `str` for text that merged, a `Clash` for lines both sides changed
    differently."""
    base_l, a_l, b_l = _lines(base), _lines(a), _lines(b)
    in_a, in_b = _matches(base_l, a_l), _matches(base_l, b_l)
    # A base line that both sides kept is an anchor; what lies between two anchors
    # is one region, changed by neither side, one side, or both.
    anchors = [i for i in range(len(base_l)) if i in in_a and i in in_b]
    anchors.append(len(base_l))
    segments: list = []
    prev_base = prev_a = prev_b = 0
    for anchor in anchors:
        end_a = in_a[anchor] if anchor < len(base_l) else len(a_l)
        end_b = in_b[anchor] if anchor < len(base_l) else len(b_l)
        region_base = base_l[prev_base:anchor]
        region_a = a_l[prev_a:end_a]
        region_b = b_l[prev_b:end_b]
        if region_a == region_b:
            chosen = region_a
        elif region_a == region_base:
            chosen = region_b
        elif region_b == region_base:
            chosen = region_a
        else:
            segments.append(Clash(region_base, region_a, region_b))
            chosen = None
        if chosen:
            text = "".join(chosen)
            if segments and isinstance(segments[-1], str):
                segments[-1] += text
            else:
                segments.append(text)
        if anchor < len(base_l):
            line = base_l[anchor]
            if segments and isinstance(segments[-1], str):
                segments[-1] += line
            else:
                segments.append(line)
        prev_base, prev_a, prev_b = anchor + 1, end_a + 1, end_b + 1
    return _end_like(segments, a)


def _same_updated_at(base: str, a: str, b: str) -> tuple[str, str, str, Optional[str]]:
    """Both computers touched `updated_at`, so it would clash on every merge. Give
    all three versions the later of the two values: the merged node was changed
    at least that late."""
    values = []
    for text in (a, b):
        header, _ = split_frontmatter(text)
        match = _UPDATED_AT.search(header or "")
        if match:
            values.append(match.group(0))
    if not values:
        return base, a, b, None
    # ISO 8601 stamps in one format sort as text.
    later = max(values, key=lambda line: line.split(":", 1)[1].strip().strip("'\""))

    def fix(text: str) -> str:
        header, body = split_frontmatter(text)
        if header is None or not _UPDATED_AT.search(header):
            return text
        start = text.find(header)
        return text[:start] + _UPDATED_AT.sub(lambda _: later, header, count=1) + text[start + len(header):]

    return fix(base), fix(a), fix(b), later


# ---------------------------------------------------------------------------
# One conflicted copy
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", newline="")
    except (OSError, UnicodeDecodeError) as e:
        raise MergeError(f"Cannot read {path.name}: {e}") from e


def _uid(text: str) -> Optional[str]:
    fm, _ = load_frontmatter(text)
    uid = (fm or {}).get("uid") if isinstance(fm, dict) else None
    return str(uid) if uid else None


def _copy_path(vault_root: Path, copy_name: str) -> Path:
    if "/" in copy_name or "\\" in copy_name or not COPY_RE.match(copy_name):
        raise MergeError(f"{copy_name!r} is not a conflicted copy in the vault.")
    path = Path(vault_root) / copy_name
    if not path.is_file():
        raise MergeError(f"{copy_name!r} is not a conflicted copy in the vault.")
    return path


def _free_name(vault_root: Path, stem: str) -> str:
    n = 2
    while (Path(vault_root) / f"{stem}-{n}.md").exists():
        n += 1
    return f"{stem}-{n}.md"


def _plan(vault_root: Path, copy_name: str) -> dict:
    copy = _copy_path(vault_root, copy_name)
    original = Path(vault_root) / original_name(copy_name)
    b = _read(copy)
    if not original.is_file():
        return {"kind": "restore", "original": original.name, "b": b}
    a = _read(original)
    if a == b:
        return {"kind": "merged", "original": original.name, "a": a, "b": b, "text": a, "segments": [a]}
    base = vault_history.merge_base_text(vault_root, original)
    uid_a, uid_b = _uid(a), _uid(b)
    if uid_a and uid_b and uid_a != uid_b:
        return {"kind": "keep-both", "original": original.name, "a": a, "b": b,
                "name": _free_name(vault_root, original.stem)}
    if base is None:
        # No common ancestor: both computers created the file. Treat it as a base
        # that holds nothing, so every differing line is a clash for the user.
        base = ""
    base, a_n, b_n, _ = _same_updated_at(base, a, b)
    return {"kind": None, "original": original.name, "a": a, "b": b,
            "segments": merge3(base, a_n, b_n)}


def _token(clashes: list) -> str:
    """A fingerprint of the clashes the user is shown. `resolve` takes it back, so
    choices made for one set of clashes are never applied to another."""
    digest = hashlib.sha256()
    for c in clashes:
        for part in ("".join(c.base), "".join(c.a), "".join(c.b)):
            digest.update(part.encode("utf-8") + b"\0")
        digest.update(b"\1")
    return digest.hexdigest()[:16]


def describe(vault_root: Path, copy_name: str) -> dict:
    """What resolving `copy_name` would do. Reads only. For `conflict`, `clashes`
    lists each clash as {a, b, base} text; the user picks "a" (the kept file) or
    "b" (the copy) for each. `token` names those clashes: give it to `resolve`."""
    plan = _plan(vault_root, copy_name)
    out = {"copy": copy_name, "original": plan["original"], "kind": plan["kind"]}
    if plan["kind"] == "restore":
        out["text"] = plan["b"]
    elif plan["kind"] == "keep-both":
        out["new_name"] = plan["name"]
    elif plan["kind"] == "merged":
        out["text"] = plan["text"]
    else:
        clashes = [s for s in plan["segments"] if isinstance(s, Clash)]
        out["kind"] = "conflict" if clashes else "merged"
        if clashes:
            out["token"] = _token(clashes)
            out["clashes"] = [{"a": "".join(c.a), "b": "".join(c.b), "base": "".join(c.base)} for c in clashes]
            out["segments"] = [
                {"text": s} if isinstance(s, str) else {"clash": sum(isinstance(x, Clash) for x in plan["segments"][:i])}
                for i, s in enumerate(plan["segments"])
            ]
        else:
            out["text"] = "".join(plan["segments"])
    return out


def resolve(vault_root: Path, copy_name: str, choices: Optional[list[str]] = None,
            token: Optional[str] = None) -> dict:
    """Merge the copy into the kept file, record it in the history, delete the
    copy. `choices` holds "a" or "b" for each clash, in file order; it must be
    given exactly when `describe` reports `conflict`. `token` is the one `describe`
    returned with the clashes the choices answer; when it is given and the files
    have changed so that the clashes differ, nothing is written. Raises MergeError."""
    # Imported here: api imports a great deal, and this module is also used by the linter.
    from loci import api

    vault_root = Path(vault_root)
    with vault_history.write_lock(vault_root):
        plan = _plan(vault_root, copy_name)
        copy = vault_root / copy_name
        original = vault_root / plan["original"]
        kind = plan["kind"]
        message = f"Merged conflicted copy of {plan['original']}"

        if kind == "keep-both":
            target = vault_root / plan["name"]
            writes = {copy: None, target: plan["b"].encode("utf-8")}
            message = f"Kept both nodes named {plan['original']}: copy saved as {target.name}"
            settle = None
        elif kind == "restore":
            writes = {copy: None, original: plan["b"].encode("utf-8")}
            message = f"Edit on the other computer overrode a delete of {plan['original']}"
            settle = original
        else:
            segments = plan["segments"]
            clashes = [s for s in segments if isinstance(s, Clash)]
            kind = "conflict" if clashes else "merged"
            choices = list(choices or [])
            if len(choices) != len(clashes) or any(c not in ("a", "b") for c in choices):
                raise MergeError(
                    f"{plan['original']} has {len(clashes)} clashing edit(s); "
                    f"give one choice, 'a' or 'b', for each (got {len(choices)})."
                )
            if token is not None and token != _token(clashes):
                raise MergeError(f"{plan['original']} changed since you looked at it. Open it again.")
            picks = iter(choices)
            text = "".join(s if isinstance(s, str) else "".join(s.a if next(picks) == "a" else s.b)
                           for s in segments)
            writes = {copy: None, original: text.encode("utf-8")}
            settle = original

        # The copy is a version nobody has recorded yet. Record it before it goes,
        # so it can be read back from the history.
        vault_history.before_write(vault_root, [copy, *writes])
        out = {"resolved": copy_name, "kind": kind}
        api._apply_files(writes, message, out, settled=[settle] if settle else [])
        for path in writes:
            if path != copy:
                api._reindex_quietly(path)
        return out
