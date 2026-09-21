"""
tests/test_tag_hygiene.py
The rules that keep tags from turning back into the September 2026 mess:
a tag that names a node belongs as a relation, a tag that repeats the type
belongs nowhere, spellings that collapse are one tag. Checked by the linter
on a vault and by api.save / api.patch on a single write (warn, never block).
"""
from collections import Counter

import pytest

from loci import api
from loci.tools import nx_graph as graph
from loci.tools import tag_hygiene as th
from loci.tools.vault_linter import lint_vault


# ---------------------------------------------------------------------------
# Pure rules
# ---------------------------------------------------------------------------

def _index():
    return th.build_name_index([
        {"uid": "p1", "type": "project", "title": "Loci"},
        {"uid": "e1", "type": "entity", "title": "Globex Corp (GLX)"},
        {"uid": "t1", "type": "topic", "title": "User Research", "aliases": ["UXR"]},
        {"uid": "old", "type": "project", "title": "Vela", "state": "archived"},
        {"uid": "s1", "type": "topic", "title": "Strategy"},
        {"uid": "s2", "type": "project", "title": "Strategy"},
        {"uid": "d1", "type": "document", "title": "Python"},   # not a link target
    ])


def test_check_tags_names_the_relation_for_each_target_type():
    warnings = th.check_tags(["loci", "glx", "uxr", "python"], "task", "feature", _index())
    by_tag = {w.tag: w for w in warnings}
    assert set(by_tag) == {"loci", "glx", "uxr"}
    assert "belongs-to" in by_tag["loci"].message and "(p1)" in by_tag["loci"].message
    assert "involves" in by_tag["glx"].message
    assert "about" in by_tag["uxr"].message
    assert all(w.code == "tag-names-node" for w in warnings)


def test_check_tags_flags_a_tag_that_repeats_type_or_subtype():
    warnings = th.check_tags(["Book", "asset", "shelf"], "asset", "book", _index())
    assert [(w.code, w.tag) for w in warnings] == [("tag-repeats-type", "Book"), ("tag-repeats-type", "asset")]


def test_check_tags_flags_the_plural_of_the_subtype_too():
    # The near-duplicate rule says books and book are one word; the
    # repeats-type rule must agree, or `books` on a book slips through.
    warnings = th.check_tags(["books"], "asset", "book", _index())
    assert [(w.code, w.tag) for w in warnings] == [("tag-repeats-type", "books")]
    warnings = th.check_tags(["bugs"], "task", "bug", _index())
    assert [(w.code, w.tag) for w in warnings] == [("tag-repeats-type", "bugs")]


def test_check_tags_compares_self_uid_as_a_string():
    # A hand-written all-digit uid loads as int; the index stores str. The
    # node must still recognise itself, or it is told to link to itself.
    index = th.build_name_index([{"uid": 12345678, "type": "project", "title": "Numbered"}])
    assert th.check_tags(["numbered"], "project", None, index, self_uid="12345678") == []


def test_check_tags_ignores_archived_targets_ambiguity_and_self():
    warnings = th.check_tags(["vela", "strategy", "loci"], "project", None, _index(), self_uid="p1")
    assert warnings == []


def test_check_tags_says_drop_not_link_when_the_edge_already_exists():
    # A task belongs-to Loci and is also tagged loci: the tag is redundant, not
    # a missing edge — asking for a belongs-to would write the edge twice.
    warnings = th.check_tags(["loci", "glx"], "task", None, _index(),
                             relations=[{"uid": "p1", "type": "belongs-to"}])
    by_tag = {w.tag: w for w in warnings}
    assert "already links to — drop the tag" in by_tag["loci"].message
    assert "belongs-to" not in by_tag["loci"].message
    assert "involves" in by_tag["glx"].message      # not linked; still asks for the edge


def test_check_tags_reads_a_scalar_tags_value_as_one_tag():
    # A hand-edited `tags: loci` is the tag "loci", not the letters l, o, c, i.
    warnings = th.check_tags("loci", "task", None, _index())
    assert [w.tag for w in warnings] == ["loci"]
    assert th.as_tag_list("rust") == ["rust"]
    assert th.as_tag_list(["a", 1]) == ["a", "1"]
    assert th.as_tag_list({"a": 1}) == [] and th.as_tag_list(None) == [] and th.as_tag_list("  ") == []
    # A dangling `-` under tags: loads as None; it is not a tag called "None".
    assert th.as_tag_list(["rust", None, "", "  "]) == ["rust"]


def test_near_duplicate_groups_fold_case_separators_and_plurals():
    counts = Counter({"acme-corp": 10, "acmecorp": 2, "open-question": 5, "open-questions": 1,
                      "C++": 3, "C#": 1, "python": 4})
    groups = th.near_duplicate_groups(counts)
    assert groups == [["acme-corp", "acmecorp"], ["open-question", "open-questions"]]


def test_near_duplicate_groups_leave_words_that_merely_end_in_s_alone():
    # sass/sas, chaos/chao, status/statu, analysis/analysi: the s is part of the word.
    counts = Counter({"sass": 2, "sas": 1, "chaos": 2, "chao": 1, "status": 2, "statu": 1,
                      "analysis": 3, "analysi": 1, "books": 2, "book": 1})
    assert th.near_duplicate_groups(counts) == [["books", "book"]]


def test_near_duplicate_groups_keep_known_false_plurals_apart():
    # https is not the plural of http; canvas is not several canva.
    counts = Counter({"http": 3, "https": 2, "canva": 1, "canvas": 4, "new": 2, "news": 5, "len": 1, "lens": 1})
    assert th.near_duplicate_groups(counts) == []


def test_near_duplicate_groups_still_fold_the_common_os_us_is_plurals():
    # An earlier suffix rule exempted every os/us/is ending to protect chaos and
    # status, and with them the plurals a tag vault actually grows.
    counts = Counter({"todo": 5, "todos": 3, "video": 4, "videos": 2, "api": 6, "apis": 1,
                      "repo": 2, "repos": 2, "kpi": 1, "kpis": 3, "wiki": 2, "wikis": 1})
    assert th.near_duplicate_groups(counts) == [
        ["todo", "todos"], ["api", "apis"], ["video", "videos"], ["kpis", "kpi"],
        ["repo", "repos"], ["wiki", "wikis"],
    ]


def test_near_duplicate_groups_prefer_lowercase_on_a_tie():
    # The first spelling is the one the linter tells the user to keep.
    counts = Counter({"Chore": 1, "chore": 1, "Acme-Corp": 2, "acme-corp": 2, "UX": 3, "ux": 1})
    assert th.near_duplicate_groups(counts) == [
        ["UX", "ux"], ["acme-corp", "Acme-Corp"], ["chore", "Chore"],
    ]


def test_singletons_are_the_tags_used_once():
    assert th.singletons(Counter({"a": 1, "b": 2, "c": 1})) == ["a", "c"]


# ---------------------------------------------------------------------------
# Linter
# ---------------------------------------------------------------------------

def test_lint_vault_warns_on_tags_that_should_be_edges_and_reports_the_census(tmp_vault):
    # The fixture project is "Knowledge Graph Platform"; tag a task with it and with its own subtype.
    from loci.tools.frontmatter import split_frontmatter
    import yaml
    p = tmp_vault / "task-review-prs.md"
    fm_text, body = split_frontmatter(p.read_text())
    fm = yaml.safe_load(fm_text)
    fm["tags"] = ["knowledge-graph-platform", "chore", "Chore", "once-only"]
    p.write_text("---\n" + yaml.safe_dump(fm) + "---" + body)

    result = lint_vault(tmp_vault)
    codes = Counter(w["code"] for w in result["warnings"] if w["path"] == "task-review-prs.md")
    assert codes["tag-names-node"] == 1
    assert codes["tag-repeats-type"] == 2
    assert not any(w["code"] == "tag-singletons" for w in result["warnings"])

    tags = result["stats"]["tags"]
    assert "once-only" in tags["singletons"]
    assert ["chore", "Chore"] in tags["near_duplicates"]
    assert any(w["code"] == "tag-near-duplicate" and w["path"] == "(vault)" for w in result["warnings"])


def test_lint_vault_reads_a_scalar_tags_value_as_one_tag(tmp_vault):
    # `tags: rust` by hand, with a topic titled "R" in the vault: no warning
    # for a tag 'r', and the census counts one tag, not four letters.
    from loci.tools.frontmatter import split_frontmatter
    import yaml
    p = tmp_vault / "task-review-prs.md"
    fm_text, body = split_frontmatter(p.read_text())
    fm = yaml.safe_load(fm_text)
    fm["tags"] = "rust"
    p.write_text("---\n" + yaml.safe_dump(fm) + "---" + body)
    (tmp_vault / "topic-r.md").write_text(
        "---\nuid: aaaa0001\ntype: topic\ntitle: R\nstate: active\ntags: []\nrelations: []\n---\n# R\n"
    )

    result = lint_vault(tmp_vault)
    assert not [w for w in result["warnings"] if w["path"] == "task-review-prs.md" and w["code"].startswith("tag-")]
    assert "rust" in result["stats"]["tags"]["singletons"]
    assert not any(len(t) == 1 for t in result["stats"]["tags"]["singletons"])


def test_lint_vault_does_not_ask_for_an_edge_the_node_already_has(tmp_vault):
    from loci.tools.frontmatter import split_frontmatter
    import yaml
    p = tmp_vault / "task-review-prs.md"
    fm_text, body = split_frontmatter(p.read_text())
    fm = yaml.safe_load(fm_text)
    fm["tags"] = ["knowledge-graph-platform"]
    fm["relations"] = [{"uid": "ddd00001", "type": "belongs-to"}]
    p.write_text("---\n" + yaml.safe_dump(fm) + "---" + body)

    [w] = [w for w in lint_vault(tmp_vault)["warnings"] if w["path"] == "task-review-prs.md" and w["code"] == "tag-names-node"]
    assert "already links to" in w["message"]


# ---------------------------------------------------------------------------
# Write time
# ---------------------------------------------------------------------------

def test_save_warns_but_still_writes_when_a_tag_names_a_node(tmp_vault):
    # No graph.get() first: a save is often the first call a process makes,
    # and the warning must not depend on whether someone searched earlier.
    assert graph._graph is None
    result = api.save(
        type="task", title="Tagged with the project", body="",
        tags=["knowledge-graph-platform", "python"],
        extra_fields={"status": "todo", "subtype": "feature"},
    )
    assert "errors" not in result and "uid" in result
    assert len(result["tag_warnings"]) == 1
    assert "belongs-to" in result["tag_warnings"][0]
    assert (tmp_vault / "tagged-with-the-project.md").exists() or any(tmp_vault.glob("tagged-with-the-project*.md"))


def test_save_without_offending_tags_carries_no_warning(tmp_vault):
    result = api.save(type="task", title="Clean", body="", tags=["python"],
                      extra_fields={"status": "todo", "subtype": "feature"})
    assert "tag_warnings" not in result


def test_patch_warns_when_a_tag_repeats_the_subtype(tmp_vault):
    result = api.patch("task-review-prs.md", {"tags": ["chore", "python"]})   # subtype chore; its uid is mnemonic, so by path
    assert result["tag_warnings"] == [
        "tag 'chore' repeats the node's own type/subtype — the field already says it; drop the tag"
    ]


def test_save_sees_a_project_added_behind_its_back(tmp_vault):
    # The index refreshes with the vault, not with whoever last built the graph.
    import os, time
    graph.get(tmp_vault)
    (tmp_vault / "project-mercury.md").write_text(
        "---\nuid: aaaa0002\ntype: project\ntitle: Mercury\nstate: active\ntags: []\nrelations: []\n---\n# Mercury\n"
    )
    later = time.time() + 5           # the staleness signal is the directory mtime
    os.utime(tmp_vault, (later, later))
    result = api.save(type="task", title="Late tag", body="", tags=["mercury"],
                      extra_fields={"status": "todo", "subtype": "feature"})
    assert "aaaa0002" in result["tag_warnings"][0]


def test_save_does_not_ask_for_an_edge_it_was_given(tmp_vault):
    result = api.save(
        type="task", title="Linked and tagged", body="", tags=["knowledge-graph-platform"],
        relations=[{"uid": "ddd00001", "type": "belongs-to"}],
        extra_fields={"status": "todo", "subtype": "feature"},
    )
    assert "already links to" in result["tag_warnings"][0]


def test_patch_persists_a_scalar_tags_value_as_a_list(tmp_vault):
    # Passed as a string, or already in the file by hand: the file ends up
    # with the list every reader expects, and the warning is for one tag.
    import yaml
    result = api.patch("task-review-prs.md", {"tags": "chore"})
    assert result["tags"] == ["chore"]
    assert result["tag_warnings"] == [
        "tag 'chore' repeats the node's own type/subtype — the field already says it; drop the tag"
    ]
    fm = yaml.safe_load((tmp_vault / "task-review-prs.md").read_text().split("---", 2)[1])
    assert fm["tags"] == ["chore"]


def test_save_still_succeeds_when_the_name_index_cannot_be_built(tmp_vault):
    # One hand-edited node with a bare string under relations makes the graph
    # build raise. The file is already written by the time the warning step
    # runs; reporting an error would leave a node the retry refuses as a
    # duplicate. Warnings are advisory — skip them, keep the result.
    (tmp_vault / "entity-broken.md").write_text(
        "---\nuid: bbbb0001\ntype: entity\ntitle: Broken\nstate: active\ntags: []\n"
        "relations:\n  - ddd00001\n---\n# Broken\n"
    )
    result = api.save(type="task", title="Saved despite it", body="", tags=["knowledge-graph-platform"],
                      extra_fields={"status": "todo", "subtype": "feature"})
    assert "errors" not in result and "uid" in result
    assert "tag_warnings" not in result
    patched = api.patch(result["path"], {"tags": ["feature"]})   # by path: uid lookup needs the graph
    assert patched["uid"] == result["uid"] and "tag_warnings" not in patched


def test_patch_does_not_tell_a_numeric_uid_node_to_link_to_itself(tmp_vault):
    # `uid: 12345678` unquoted loads as int. The node is tagged with its own
    # name; the only match in the index is itself, and that is not a warning.
    (tmp_vault / "project-numbered.md").write_text(
        "---\nuid: 12345678\ntype: project\ntitle: Numbered\nstate: active\ntags: []\nrelations: []\n---\n# Numbered\n"
    )
    result = api.patch("project-numbered.md", {"tags": ["numbered"]})
    assert "tag_warnings" not in result


def test_a_batch_of_saves_does_not_rebuild_the_graph_each_time(tmp_vault, monkeypatch):
    # The name index is taken before the write, and the write is then marked
    # as applied, so the mtime bump a save makes is not read as "files
    # changed behind my back". Before: N saves, N full re-parses of the vault.
    import os, time
    graph.get(tmp_vault)
    builds = []
    real_build = graph._build
    monkeypatch.setattr(graph, "_build", lambda root: builds.append(root) or real_build(root))
    for i in range(3):
        result = api.save(type="task", title=f"Batch item {i}", body="", tags=["knowledge-graph-platform"],
                          extra_fields={"status": "todo", "subtype": "feature"})
        assert "belongs-to" in result["tag_warnings"][0]
        # Each save's node is in the graph, and a later save can name it.
        assert graph.get(tmp_vault).has_node(result["uid"])
    assert builds == []
    patched = api.patch(result["path"], {"tags": ["feature"]})
    assert "repeats the node's own type/subtype" in patched["tag_warnings"][0]
    asset = api.save_asset(content=b"%PDF-1", format="pdf", mime_type="application/pdf",
                           title="Batched book", node_type="asset", subtype="book", tags=["book"])
    assert "repeats the node's own type/subtype" in asset["tag_warnings"][0]
    assert builds == []
    # An outside write is still noticed: the freshness mark covers only what
    # this process wrote.
    (tmp_vault / "project-outside.md").write_text(
        "---\nuid: aaaa0003\ntype: project\ntitle: Outside\nstate: active\ntags: []\nrelations: []\n---\n# Outside\n"
    )
    later = time.time() + 5
    os.utime(tmp_vault, (later, later))
    assert graph.get(tmp_vault).has_node("aaaa0003")
    assert builds == [tmp_vault]


def test_save_asset_warns_like_save_does(tmp_vault):
    result = api.save_asset(
        content=b"%PDF-1", format="pdf", mime_type="application/pdf",
        title="A book tagged book", node_type="asset", subtype="book", tags=["book", "knowledge-graph-platform"],
    )
    assert "uid" in result
    assert len(result["tag_warnings"]) == 2
    assert any("repeats the node's own type/subtype" in w for w in result["tag_warnings"])
    assert any("belongs-to" in w for w in result["tag_warnings"])
