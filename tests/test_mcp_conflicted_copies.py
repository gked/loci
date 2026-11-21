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


def ask(name, *args, **kw):
    """The call an agent makes once the user has said yes."""
    return mcp_server.resolve_conflicted_copy(name, *args, user_confirmed=True, **kw)


def test_nothing_is_written_until_the_user_confirmed(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a="ONE\ntwo\nthree\nfour\nfive\n", b="one\ntwo\nthree\nfour\nFIVE\n")
    token = mcp_server.list_conflicted_copies()["copies"][0]["token"]
    refused = mcp_server.resolve_conflicted_copy(copy.name, None, token)
    assert "Ask the user first" in refused["error"] and copy.exists()


def test_a_clean_merge_through_the_tools(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a="ONE\ntwo\nthree\nfour\nfive\n", b="one\ntwo\nthree\nfour\nFIVE\n")
    listed = mcp_server.list_conflicted_copies()["copies"]
    assert [c["copy"] for c in listed] == [copy.name]
    assert listed[0]["kind"] == "merged" and listed[0]["token"]

    assert "token is required" in ask(copy.name)["error"] and copy.exists()
    done = ask(copy.name, None, listed[0]["token"])
    assert done["kind"] == "merged" and not copy.exists()
    assert "ONE" in node.read_text(encoding="utf-8") and "FIVE" in node.read_text(encoding="utf-8")
    assert mcp_server.list_conflicted_copies() == {"copies": []}


def test_a_clash_needs_a_choice_per_clash_and_a_token(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("three", "AAA"), b=BASE.replace("three", "BBB"))
    listed = mcp_server.list_conflicted_copies()["copies"][0]
    assert listed["kind"] == "conflict" and len(listed["clashes"]) == 1

    assert "error" in ask(copy.name, None, listed["token"]) and copy.exists()    # no choice: the tool never guesses
    assert "token is required" in ask(copy.name, ["b"])["error"] and copy.exists()   # no token: not applied blind

    done = ask(copy.name, ["b"], listed["token"])
    assert done["kind"] == "conflict" and "BBB" in node.read_text(encoding="utf-8") and not copy.exists()


def test_a_stale_token_is_refused(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("three", "AAA"), b=BASE.replace("three", "BBB"))
    listed = mcp_server.list_conflicted_copies()["copies"][0]
    copy.write_text(copy.read_text(encoding="utf-8").replace("BBB", "CCC"), newline="\n", encoding="utf-8")               # changed since the listing
    refused = ask(copy.name, ["a"], listed["token"])
    assert "changed since" in refused["error"] and copy.exists()


def test_a_merged_copy_that_changed_since_the_listing_is_refused(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a="ONE\ntwo\nthree\nfour\nfive\n", b="one\ntwo\nthree\nfour\nFIVE\n")
    token = mcp_server.list_conflicted_copies()["copies"][0]["token"]
    copy.write_text(copy.read_text(encoding="utf-8").replace("FIVE", "SIX"), newline="\n", encoding="utf-8")
    assert "changed since" in ask(copy.name, None, token)["error"] and copy.exists()


def test_restore_and_keep_both_through_the_tools(tmp_vault, as_computer):
    node, copy = diverge(tmp_vault, as_computer, a=BASE, b=BASE.replace("three", "BBB"))
    node.unlink()                                                          # deleted on the other computer
    listed = mcp_server.list_conflicted_copies()["copies"][0]
    assert listed["kind"] == "restore"
    assert "takes no choices" in ask(copy.name, ["a"], listed["token"])["error"] and copy.exists()
    done = ask(copy.name, None, listed["token"])
    assert done["kind"] == "restore" and "BBB" in node.read_text(encoding="utf-8") and not copy.exists()


def test_one_unreadable_copy_does_not_hide_the_others(tmp_vault, as_computer, monkeypatch):
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("three", "AAA"), b=BASE.replace("three", "BBB"))
    other = tmp_vault / "other (conflicted copy 2026-11-15 101010).md"
    other.write_bytes(b"\xff\xfe\x00 not utf-8")
    real = node_merge.describe

    def flaky(root, name):
        if name == copy.name:
            import yaml
            raise yaml.YAMLError("bad frontmatter")
        return real(root, name)

    monkeypatch.setattr(node_merge, "describe", flaky)
    listed = mcp_server.list_conflicted_copies()["copies"]
    assert {c["copy"]: c["kind"] for c in listed} == {copy.name: "error", other.name: "error"}


def test_a_yaml_error_while_resolving_is_an_error_not_a_crash(tmp_vault, as_computer, monkeypatch):
    import yaml
    node, copy = diverge(tmp_vault, as_computer, a=BASE.replace("three", "AAA"), b=BASE.replace("three", "BBB"))
    monkeypatch.setattr(node_merge, "resolve", lambda *a, **k: (_ for _ in ()).throw(yaml.YAMLError("bad")))
    assert "error" in ask(copy.name, ["a"], "x")


def test_an_unknown_copy_is_an_error_not_a_crash(tmp_vault):
    assert "error" in ask("nothing (conflicted copy 2026-01-01 000000).md")
