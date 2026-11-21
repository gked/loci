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
