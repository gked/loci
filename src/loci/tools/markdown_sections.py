"""Split Markdown node bodies into heading-aware, read-time chunks."""

from __future__ import annotations

import re


def estimated_tokens(text: str) -> int:
    """A rough, model-independent token estimate: four characters per token.

    One definition for the whole read path, so a node's estimate and its
    chunks' estimates are the same arithmetic.
    """
    return (len(text) + 3) // 4


# A closing hash run only ends a heading when whitespace precedes it, so
# "# C#" is the title C#, while "## Findings ##" is the title Findings.
_ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+|$)(.*?)(?:[ \t]+#+)?[ \t]*$")
# A fence line: the marker, then whatever follows it. An info string (```js) is
# legal only on an opening fence, so `rest` is what tells an open from a close.
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _heading_sections(body: str, max_chars: int) -> list[tuple[list[str], str]]:
    """Return contiguous heading sections, ignoring heading-like text in fences."""
    sections: list[tuple[list[str], str]] = []
    heading_stack: list[tuple[int, str]] = []
    current_path: list[str] = []
    current: list[str] = []
    fence_char = ""
    fence_length = 0

    for line in body.splitlines(keepends=True):
        fence_match = _FENCE.match(line.rstrip("\r\n"))
        if fence_char:
            if fence_match:
                marker, rest = fence_match.group(1), fence_match.group(2)
                # A closing fence carries nothing but the marker: ```js inside a
                # block is still code, so a heading-like line after it is too.
                closes = (
                    marker[0] == fence_char
                    and len(marker) >= fence_length
                    and not rest.strip()
                )
                if closes:
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
    if (
        len(sections) > 1
        and sections[0][0] == []
        and not sections[0][1].strip()
        and len(sections[0][1]) <= max_chars      # a longer flood would spend
    ):                                            # many ids under the wrong heading
        preamble = sections.pop(0)[1]
        path, text = sections[0]
        sections[0] = (path, preamble + text)
    return sections


def _is_heading_only(text: str) -> bool:
    """True when this piece is a heading line and nothing else."""
    stripped = text.strip()
    if not stripped or "\n" in stripped:
        return False
    return bool(_ATX_HEADING.match(stripped))


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
            remaining = paragraph
            if current:
                # A heading is its own paragraph, so flushing here would make it
                # a chunk of its own. Let it ride with the first piece of the
                # text it titles instead.
                if _is_heading_only(current):
                    remaining = current + paragraph
                else:
                    chunks.append(current)
                current = ""
            while len(remaining) > max_chars:
                # rfind stops before max_chars, so cut <= max_chars always: a
                # newline sitting exactly on the limit must not push a chunk over.
                cut = remaining.rfind("\n", 0, max_chars)
                cut = cut + 1 if cut >= 0 else max_chars
                # A line-boundary cut right after the section's heading would
                # leave the heading as a chunk of its own: an id whose excerpt
                # is empty and whose body sits in the next chunk. Keep the
                # heading with the text it titles and cut at the limit instead.
                if _is_heading_only(remaining[:cut]):
                    cut = max_chars
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
    for heading_path, section_text in _heading_sections(body, max_chars):
        parts = _split_text(section_text, max_chars)
        for part_number, text in enumerate(parts, start=1):
            chunks.append({
                "id": f"chunk-{len(chunks) + 1}",
                "heading_path": heading_path,
                "part": part_number,
                "parts": len(parts),
                "text": text,
                "estimated_tokens": estimated_tokens(text),
            })
    return chunks
