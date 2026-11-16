"""
The two MCP tools for conflicted copies, and the loci-save skill that names them.
"""

import re
from pathlib import Path

import pytest

from loci import mcp_server
from loci.tools import node_merge

from test_node_merge import BASE, as_computer, diverge, history_on  # noqa: F401  (fixtures)


def test_the_skill_names_only_tools_that_exist():
    registered = set(mcp_server.mcp._tool_manager._tools)
    assert {"list_conflicted_copies", "resolve_conflicted_copy"} <= registered
    for name in ("SKILL.md", "SKILL.ru-RU.md"):
        skill = Path(mcp_server.__file__).parent / "skills" / "loci-save" / name
        named = set(re.findall(r"loci__(\w+conflicted_cop\w+)", skill.read_text(encoding="utf-8")))
        assert named == {"list_conflicted_copies", "resolve_conflicted_copy"}, name


def test_an_empty_vault_lists_nothing(tmp_vault):
    assert mcp_server.list_conflicted_copies() == {"copies": []}


def test_a_clean_merge_through_the_tools(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a="ONE\ntwo\nthree\nfour\nfive\n", b="one\ntwo\nthree\nfour\nFIVE\n")
    listed = mcp_server.list_conflicted_copies()["copies"]
    assert [c["copy"] for c in listed] == [copy.name]
    assert listed[0]["kind"] == "merged"

    done = mcp_server.resolve_conflicted_copy(copy.name)
    assert done["kind"] == "merged" and not copy.exists()
    assert "ONE" in node.read_text() and "FIVE" in node.read_text()
    assert mcp_server.list_conflicted_copies() == {"copies": []}


def test_a_clash_needs_a_choice_per_clash(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("three", "AAA"), b=BASE.replace("three", "BBB"))
    listed = mcp_server.list_conflicted_copies()["copies"][0]
    assert listed["kind"] == "conflict" and len(listed["clashes"]) == 1

    refused = mcp_server.resolve_conflicted_copy(copy.name)               # no choice: the tool never guesses
    assert "error" in refused and copy.exists()

    done = mcp_server.resolve_conflicted_copy(copy.name, ["b"], listed["token"])
    assert done["kind"] == "conflict" and "BBB" in node.read_text() and not copy.exists()


def test_a_stale_token_is_refused(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("three", "AAA"), b=BASE.replace("three", "BBB"))
    listed = mcp_server.list_conflicted_copies()["copies"][0]
    copy.write_text(copy.read_text().replace("BBB", "CCC"))               # changed since the listing
    refused = mcp_server.resolve_conflicted_copy(copy.name, ["a"], listed["token"])
    assert "changed since" in refused["error"] and copy.exists()


def test_an_unknown_copy_is_an_error_not_a_crash(tmp_vault):
    assert "error" in mcp_server.resolve_conflicted_copy("nothing (conflicted copy 2026-01-01 000000).md")
