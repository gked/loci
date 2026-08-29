"""
frontmatter.py
Shared parsing for the YAML frontmatter block at the top of every vault node.

Why this exists: the obvious `raw.split("---", 2)` is wrong. It splits on the
first `---` *substring* anywhere in the file, including one that appears inside
a frontmatter value — a markdown horizontal rule inside a quoted scalar, say.
When that happens the frontmatter is truncated mid-value and every reader
(list_vault, lint_vault, the graph loader) fails on the same file with an
opaque "found unexpected end of stream". Only a line that is exactly `---`
closes the block, so that is what we match.
"""

import yaml
from typing import Optional


FENCE = "---"


def split_frontmatter(raw: str) -> tuple[Optional[str], str]:
    """
    Split a vault file into (frontmatter_text, body).

    Returns (None, raw) when the file has no frontmatter block, or when the
    opening fence is never closed.

    The returned body keeps the newline that terminates the closing fence,
    matching what the old raw.split("---", 2)[2] produced — downstream regexes
    anchor on that leading newline.
    """
    first_nl = raw.find("\n")
    if first_nl == -1 or raw[:first_nl].rstrip() != FENCE:
        return None, raw

    pos = first_nl + 1
    while pos <= len(raw):
        nl = raw.find("\n", pos)
        line_end = len(raw) if nl == -1 else nl
        if raw[pos:line_end].rstrip() == FENCE:
            return raw[first_nl + 1:pos], ("" if nl == -1 else raw[line_end:])
        if nl == -1:
            break
        pos = nl + 1

    return None, raw


def load_frontmatter(raw: str) -> tuple[Optional[dict], str]:
    """
    Split and YAML-parse in one step.

    Returns (frontmatter_dict, body). The dict is None when there is no
    frontmatter block, when the YAML is malformed, or when it parses to
    something other than a mapping — callers that need the parse error itself
    should use split_frontmatter and call yaml.safe_load directly.
    """
    fm_text, body = split_frontmatter(raw)
    if fm_text is None:
        return None, body
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None, body
    if fm is None:
        return {}, body
    if not isinstance(fm, dict):
        return None, body
    return fm, body
