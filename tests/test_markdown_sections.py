import pytest

from loci.tools.markdown_sections import split_markdown_sections


def test_split_markdown_sections_tracks_heading_hierarchy():
    body = """Opening.

# Overview
Top-level text.

## Findings
Observed result.

# Next steps
Follow up.
"""

    chunks = split_markdown_sections(body, max_chars=1000)

    assert [chunk["heading_path"] for chunk in chunks] == [
        [], ["Overview"], ["Overview", "Findings"], ["Next steps"]
    ]
    assert [chunk["text"].strip() for chunk in chunks] == [
        "Opening.", "# Overview\nTop-level text.",
        "## Findings\nObserved result.", "# Next steps\nFollow up."
    ]


def test_split_markdown_sections_ignores_headings_inside_fenced_code():
    body = """# Real heading

```markdown
## Not a heading
```

After the fence.
"""

    chunks = split_markdown_sections(body, max_chars=1000)

    assert len(chunks) == 1
    assert chunks[0]["heading_path"] == ["Real heading"]
    assert "## Not a heading" in chunks[0]["text"]


def test_split_markdown_sections_ignores_a_closing_fence_with_an_info_string():
    """An info string is only legal on an opening fence, so ```js does not close
    a block — a heading-like line after it is still code, not a section."""
    body = "# Real\n\n```\ncode line\n```js\n# inside the code block\nmore code\n```\n\nAfter.\n"

    chunks = split_markdown_sections(body, max_chars=1000)

    assert len(chunks) == 1
    assert chunks[0]["heading_path"] == ["Real"]
    assert "".join(chunk["text"] for chunk in chunks) == body


def test_split_markdown_sections_splits_a_crlf_body_at_paragraph_boundaries():
    """A CRLF body (a Windows-written vault, or a history snapshot read without
    newline translation) must still break between paragraphs, not mid-paragraph."""
    paragraphs = [f"Paragraph {i} first line.\r\nParagraph {i} second line.\r\n\r\n" for i in range(4)]
    body = "# Windows\r\n\r\n" + "".join(paragraphs)

    chunks = split_markdown_sections(body, max_chars=60)

    assert len(chunks) > 1
    assert "".join(chunk["text"] for chunk in chunks) == body
    assert all(chunk["text"].endswith("\r\n\r\n") for chunk in chunks[:-1])


def test_split_markdown_sections_folds_a_blank_preamble_into_the_first_section():
    """A blank opening line must not become a chunk id carrying nothing."""
    body = "\n\n# Heading\n\nReal content.\n"

    chunks = split_markdown_sections(body, max_chars=1000)

    assert len(chunks) == 1
    assert chunks[0]["heading_path"] == ["Heading"]
    assert "".join(chunk["text"] for chunk in chunks) == body


def test_split_markdown_sections_requires_a_matching_fence_to_close_a_block():
    """A fence closes only with the same character and at least the same length,
    so a nested or mismatched fence leaves the block open."""
    tilde_inside = "# A\n\n```\ncode\n~~~\n# still code\n```\n\nAfter.\n"
    short_inside = "# A\n\n````\ncode\n```\n# still code\n````\n\nAfter.\n"

    for body in (tilde_inside, short_inside):
        chunks = split_markdown_sections(body, max_chars=1000)
        assert len(chunks) == 1, body
        assert chunks[0]["heading_path"] == ["A"], body
        assert "".join(chunk["text"] for chunk in chunks) == body


def test_split_markdown_sections_rejects_a_nonpositive_limit():
    with pytest.raises(ValueError, match="positive"):
        split_markdown_sections("# A\n\nbody\n", max_chars=0)


def test_split_markdown_sections_keeps_a_trailing_hash_run_out_of_the_heading():
    """A closed ATX heading (`## Findings ##`) names 'Findings'; a hash that is
    part of the title (`# C#`) stays in it."""
    chunks = split_markdown_sections("## Findings ##\n\nbody\n\n# C#\n\nmore\n", 1000)

    assert [chunk["heading_path"] for chunk in chunks] == [["Findings"], ["C#"]]


def test_split_markdown_sections_estimates_tokens_for_every_chunk():
    chunks = split_markdown_sections("# A\n\n" + ("word " * 100), max_chars=200)

    assert all(chunk["estimated_tokens"] >= 1 for chunk in chunks)
    assert all(
        chunk["estimated_tokens"] == -(-len(chunk["text"]) // 4) for chunk in chunks
    )


def test_split_markdown_sections_keeps_a_heading_with_the_text_it_titles():
    """A cut straight after the heading line would leave an id whose excerpt is
    empty and whose body is in the next chunk."""
    body = "# Alpha\n" + ("Alpha body sentence. " * 30)

    chunks = split_markdown_sections(body, max_chars=160)

    assert len(chunks) > 1
    assert chunks[0]["text"].startswith("# Alpha\n")
    assert "Alpha body sentence." in chunks[0]["text"]
    assert all(len(chunk["text"]) <= 160 for chunk in chunks)
    assert "".join(chunk["text"] for chunk in chunks) == body


def test_split_markdown_sections_cuts_an_oversized_paragraph_at_a_line_boundary():
    """Line-boundary cutting is the fallback that keeps chunks readable; a blind
    character cut satisfies the size bound too, so pin the boundary itself."""
    body = "# H\n\n" + "".join(f"line {i} of one long paragraph\n" for i in range(40))

    chunks = split_markdown_sections(body, max_chars=120)

    assert len(chunks) > 1
    assert "".join(chunk["text"] for chunk in chunks) == body
    # Every chunk but the last ends exactly at a newline, not mid-line.
    assert all(chunk["text"].endswith("\n") for chunk in chunks[:-1])


def test_split_markdown_sections_does_not_fold_a_preamble_longer_than_the_budget():
    """Folding a short blank preamble saves an empty id; folding a long one would
    spend many ids on whitespace and label them with the first real heading."""
    body = ("\n" * 400) + "# H\n\nreal content\n"

    chunks = split_markdown_sections(body, max_chars=100)

    assert chunks[0]["heading_path"] == []
    assert any(chunk["heading_path"] == ["H"] for chunk in chunks)
    assert "".join(chunk["text"] for chunk in chunks) == body


def test_split_markdown_sections_never_exceeds_max_chars_at_a_newline_boundary():
    """A newline sitting exactly on the limit must not push a chunk one char over."""
    body = ("a" * 10) + "\n" + ("b" * 25)

    chunks = split_markdown_sections(body, max_chars=10)

    assert all(len(chunk["text"]) <= 10 for chunk in chunks)
    assert "".join(chunk["text"] for chunk in chunks) == body


def test_split_markdown_sections_subdivides_oversized_heading_content():
    body = """# Notes

First paragraph.

Second paragraph.

Third paragraph.
"""

    chunks = split_markdown_sections(body, max_chars=22)

    assert len(chunks) > 1
    assert all(chunk["heading_path"] == ["Notes"] for chunk in chunks)
    assert "".join(chunk["text"] for chunk in chunks) == body
    assert all(len(chunk["text"]) <= 22 for chunk in chunks)
    assert [chunk["part"] for chunk in chunks] == list(range(1, len(chunks) + 1))
