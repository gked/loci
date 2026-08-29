"""
tests/test_frontmatter.py
Frontmatter splitting: the shared helper, and the vault-level regression it fixes.

The bug this guards against: a '---' inside a frontmatter *value* (a markdown
horizontal rule in a quoted scalar) made raw.split("---", 2) cut the block short,
so the node failed to parse for every reader at once — list_vault, lint_vault,
and the graph builder all reported "found unexpected end of stream".
"""

import textwrap

import pytest
import yaml

from loci.tools.frontmatter import load_frontmatter, split_frontmatter


# ---------------------------------------------------------------------------
# split_frontmatter
# ---------------------------------------------------------------------------

def test_splits_a_normal_node():
    raw = "---\ntitle: Hello\n---\n\nBody text\n"
    fm_text, body = split_frontmatter(raw)
    assert yaml.safe_load(fm_text) == {"title": "Hello"}
    assert body == "\n\nBody text\n"


def test_body_keeps_the_newline_that_ends_the_fence():
    """Downstream regexes anchor on '\\n\\n---'; the old split produced that."""
    raw = "---\ntitle: X\n---\n\n---\nasset_path: /p/f.txt\n---\n\nhello"
    _, body = split_frontmatter(raw)
    assert body.startswith("\n\n---\nasset_path:")


def test_horizontal_rule_inside_a_value_does_not_end_the_block():
    """The actual bug: '---' as a line inside a quoted scalar."""
    raw = textwrap.dedent("""\
        ---
        title: Node with a rule in its body field
        summary: 'Intro paragraph.

          ---

          Second paragraph after a horizontal rule.'
        uid: aaaabbbb
        ---

        Real body.
        """)
    fm_text, body = split_frontmatter(raw)
    fm = yaml.safe_load(fm_text)
    assert fm["uid"] == "aaaabbbb"
    assert "---" in fm["summary"]
    assert body.strip() == "Real body."


def test_indented_rule_inside_a_value_does_not_end_the_block():
    """A '---' indented as YAML block continuation is still not a fence."""
    raw = "---\nsummary: 'a\n\n  ---\n\n  b'\nuid: ccccdddd\n---\n\nBody.\n"
    fm_text, _ = split_frontmatter(raw)
    assert yaml.safe_load(fm_text)["uid"] == "ccccdddd"


def test_no_frontmatter_returns_none_and_the_whole_text():
    raw = "# Just markdown\n\nNo frontmatter here.\n"
    assert split_frontmatter(raw) == (None, raw)


def test_unclosed_fence_returns_none():
    raw = "---\ntitle: Never closed\n\nstill going\n"
    assert split_frontmatter(raw) == (None, raw)


def test_fence_as_final_line_yields_empty_body():
    fm_text, body = split_frontmatter("---\ntitle: X\n---")
    assert yaml.safe_load(fm_text) == {"title": "X"}
    assert body == ""


def test_dashes_that_are_not_alone_on_a_line_are_not_a_fence():
    raw = "---\ntitle: em---dash\n---\n\nBody.\n"
    fm_text, _ = split_frontmatter(raw)
    assert yaml.safe_load(fm_text) == {"title": "em---dash"}


# ---------------------------------------------------------------------------
# load_frontmatter
# ---------------------------------------------------------------------------

def test_load_returns_dict_and_body():
    fm, body = load_frontmatter("---\nuid: abcd1234\n---\n\nBody.\n")
    assert fm == {"uid": "abcd1234"}
    assert body.strip() == "Body."


def test_load_returns_none_on_malformed_yaml():
    fm, _ = load_frontmatter("---\ntitle: 'unterminated\n---\n\nBody.\n")
    assert fm is None


def test_load_returns_none_when_frontmatter_is_not_a_mapping():
    fm, _ = load_frontmatter("---\n- just\n- a\n- list\n---\n\nBody.\n")
    assert fm is None


def test_load_returns_empty_dict_for_an_empty_block():
    fm, body = load_frontmatter("---\n---\n\nBody.\n")
    assert fm == {}
    assert body.strip() == "Body."


def test_load_returns_none_when_there_is_no_block():
    fm, body = load_frontmatter("plain text")
    assert fm is None
    assert body == "plain text"


# ---------------------------------------------------------------------------
# Vault-level regression: one bad node must not break the whole vault
# ---------------------------------------------------------------------------

NODE_WITH_RULE = textwrap.dedent("""\
    ---
    archived_at: null
    author: self
    created_at: '2026-08-10T00:00:00Z'
    domains: []
    references: []
    relations: []
    state: active
    status: evergreen
    summary: 'Opening line.

      ---

      Closing line after a horizontal rule.'
    tags: []
    title: Node whose summary contains a horizontal rule
    type: document
    uid: 5eaf00d5
    updated_at: '2026-08-10T00:00:00Z'
    ---

    Body of the node.
    """)


@pytest.fixture
def vault_with_rule_node(tmp_vault):
    (tmp_vault / "node-with-rule.md").write_text(NODE_WITH_RULE, encoding="utf-8")
    return tmp_vault


def test_lint_does_not_report_invalid_yaml_for_a_rule_in_a_value(vault_with_rule_node):
    from loci.tools.vault_linter import lint_vault
    result = lint_vault(vault_with_rule_node)
    offending = [
        e for e in result["errors"]
        if e["path"] == "node-with-rule.md" and e["code"] in {"invalid-yaml", "malformed-frontmatter"}
    ]
    assert offending == [], offending


def test_list_vault_includes_the_rule_node(vault_with_rule_node):
    from loci import api
    listing = api.list_items()
    assert "node-with-rule.md" in listing.get("document", [])


def test_graph_indexes_the_rule_node(vault_with_rule_node):
    from loci.tools import nx_graph
    g = nx_graph.get(vault_with_rule_node)
    assert g.has_node("5eaf00d5")
    assert g.nodes["5eaf00d5"]["title"] == "Node whose summary contains a horizontal rule"


def test_read_vault_returns_the_rule_node_intact(vault_with_rule_node):
    from loci import api
    raw = api.get("node-with-rule.md")
    fm, body = load_frontmatter(raw)
    assert fm["uid"] == "5eaf00d5"
    assert "Body of the node." in body
