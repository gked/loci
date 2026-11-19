"""
tests/test_appledouble_files.py
macOS writes a `._name` AppleDouble file next to a file it copies onto a volume
that keeps no extended attributes (tar, zip, SMB, exFAT, a sync client). In a
vault that makes `._note.md`: a binary file whose name matches `*.md` but which
is not a note. Every reader of the vault has to step over it.
"""

import pytest

from loci import api
from loci.tools.vault_files import is_appledouble
from loci.tools import directory_scanner, nx_graph, vault_history, vault_linter, write_file

# The real header of an AppleDouble file: magic, version, "Mac OS X" filler, then
# bytes that are not UTF-8.
APPLEDOUBLE = bytes.fromhex("0005160700020000") + b"Mac OS X        " + bytes([0x8F, 0x80, 0xFF]) * 40


@pytest.fixture
def vault_with_junk(tmp_vault):
    # Not `sorted(...)[0]`: a fixture copied through macOS `tar` can already hold `._` files.
    real = sorted(p for p in tmp_vault.glob("*.md") if not p.name.startswith("._"))[0]
    junk = tmp_vault / f"._{real.name}"
    junk.write_bytes(APPLEDOUBLE)
    return tmp_vault, real, junk


def test_is_appledouble_matches_only_the_dot_underscore_prefix(tmp_path):
    assert is_appledouble("._note.md")
    assert is_appledouble(tmp_path / "sub" / "._note.md")
    assert not is_appledouble("note.md")
    assert not is_appledouble("_note.md")
    assert not is_appledouble(".note.md")
    assert not is_appledouble("a._b.md")


def test_list_items_skips_an_appledouble_file(vault_with_junk):
    _, real, junk = vault_with_junk
    listed = {name for names in api.list_items().values() for name in names}
    assert real.name in listed
    assert junk.name not in listed


def test_lint_does_not_count_an_appledouble_file_as_a_node(vault_with_junk):
    vault, _, junk = vault_with_junk
    report = vault_linter.lint_vault(vault)
    assert junk.name not in str(report)


def test_the_duplicate_search_steps_over_an_appledouble_file(vault_with_junk):
    vault, _, _ = vault_with_junk
    assert write_file.check_duplicate(vault, "A title nobody used") is None


def test_the_graph_does_not_hold_an_appledouble_file(vault_with_junk):
    vault, _, junk = vault_with_junk
    nx_graph.invalidate()
    graph = nx_graph.get(vault)
    assert all(junk.name not in str(data) for _, data in graph.nodes(data=True))


def test_the_asset_index_steps_over_an_appledouble_file(vault_with_junk):
    vault, _, _ = vault_with_junk
    directory_scanner._local_path_index(vault)          # must not raise


def test_history_does_not_record_an_appledouble_file(vault_with_junk, monkeypatch):
    monkeypatch.setenv("LOCI_VAULT_HISTORY", "1")      # off by default in the suite
    from dulwich.object_store import tree_lookup_path
    from dulwich.repo import Repo

    vault, _, junk = vault_with_junk
    assert not vault_history._eligible(junk.relative_to(vault))
    api.save("document", "History after junk", "body", extra_fields={"status": "draft", "subtype": "note"})
    repo = Repo(str(vault_history.history_dir(vault)))
    tree = repo[repo.refs[vault_history.own_ref()]].tree
    with pytest.raises(KeyError):
        tree_lookup_path(repo.object_store.__getitem__, tree, junk.name.encode())
