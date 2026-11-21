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
