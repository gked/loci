"""Split Markdown node bodies into heading-aware, read-time chunks."""

from __future__ import annotations

import math
import re

_ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+|$)(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _heading_sections(body: str) -> list[tuple[list[str], str]]:
    """Return contiguous heading sections, ignoring heading-like text in fences."""
    sections: list[tuple[list[str], str]] = []
    heading_stack: list[tuple[int, str]] = []
    current_path: list[str] = []
    current: list[str] = []
    fence_char = ""
    fence_length = 0

    for line in body.splitlines(keepends=True):
        fence_match = _FENCE.match(line)
        if fence_char:
            if fence_match:
                marker = fence_match.group(1)
                if marker[0] == fence_char and len(marker) >= fence_length:
                    fence_char = ""
                    fence_length = 0
            current.append(line)
            continue
        if fence_match:
            marker = fence_match.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            current.append(line)
            continue

        heading = _ATX_HEADING.match(line.rstrip("\r\n"))
        if not heading:
            current.append(line)
            continue

        if current:
            sections.append((current_path, "".join(current)))
        level = len(heading.group(1))
        title = heading.group(2).strip()
        heading_stack = [(old_level, name) for old_level, name in heading_stack if old_level < level]
        heading_stack.append((level, title))
        current_path = [name for _, name in heading_stack]
        current = [line]

    if current:
        sections.append((current_path, "".join(current)))

    # A note that opens with a blank line produces a whitespace-only preamble
    # section. As its own chunk it is an id that carries nothing and an empty
    # excerpt, so fold it into the first real section instead — the text is kept
    # verbatim, so the chunks still rejoin to the original body.
    if len(sections) > 1 and sections[0][0] == [] and not sections[0][1].strip():
        preamble = sections.pop(0)[1]
        path, text = sections[0]
        sections[0] = (path, preamble + text)
    return sections


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split at paragraph boundaries where possible, preserving all characters."""
    if len(text) <= max_chars:
        return [text]

    # Keep blank-line separators attached to the preceding paragraph so joining
    # the returned pieces reproduces the input exactly. \r is matched explicitly:
    # a CRLF body (a vault written on Windows, or a history snapshot read without
    # newline translation) would otherwise look like one unbroken paragraph and
    # lose paragraph-aware splitting.
    paragraphs = re.findall(r".*?(?:\r?\n[ \t]*\r?\n|$)", text, flags=re.DOTALL)
    paragraphs = [part for part in paragraphs if part]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            remaining = paragraph
            while len(remaining) > max_chars:
                # rfind stops before max_chars, so cut <= max_chars always: a
                # newline sitting exactly on the limit must not push a chunk over.
                cut = remaining.rfind("\n", 0, max_chars)
                cut = cut + 1 if cut >= 0 else max_chars
                chunks.append(remaining[:cut])
                remaining = remaining[cut:]
            current = remaining
        elif len(current) + len(paragraph) > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current += paragraph

    if current:
        chunks.append(current)
    return chunks


def split_markdown_sections(body: str, max_chars: int) -> list[dict]:
    """Split a Markdown body into heading-aware chunks no longer than max_chars.

    A chunk represents the text from one heading up to (but not including) the
    next heading. Very long sections are split at blank lines, then line
    boundaries where possible. `heading_path` provides context for continuation
    chunks and `estimated_tokens` is a rough English-text estimate, not a model
    tokenizer count.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be a positive integer")

    chunks: list[dict] = []
    for heading_path, section_text in _heading_sections(body):
        parts = _split_text(section_text, max_chars)
        for part_number, text in enumerate(parts, start=1):
            chunks.append({
                "id": f"chunk-{len(chunks) + 1}",
                "heading_path": heading_path,
                "part": part_number,
                "parts": len(parts),
                "text": text,
                "estimated_tokens": math.ceil(len(text) / 4),
            })
    return chunks
