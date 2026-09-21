"""
tests/test_tags_to_relations.py
scripts/migrate_tags_to_relations.py — tags that name a node become edges.

The script is the second half of the tag cleanup (task 8e50477e): subtypes
took the "kind of thing" tags out, this takes the "which project / who /
what subject" tags out. What matters is that it links to the right node with
the right relation, never doubles an edge, never links a node to itself,
refuses to guess between two candidates, and writes a vault the linter still
accepts.
"""
import sys
from pathlib import Path

import yaml

from loci.tools.frontmatter import split_frontmatter
from loci.tools.vault_linter import lint_vault

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import migrate_tags_to_relations as mig  # noqa: E402  (must follow sys.path insert)
from loci.tools import tag_hygiene  # noqa: E402  — the matching the script now shares with the linter


BASE = {
    "author": "self", "state": "active",
    "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
    "archived_at": None, "domains": ["technology-engineering"], "summary": "s",
    "references": [],
}


def _node(vault: Path, name: str, **fm) -> dict:
    full = {**BASE, "relations": [], "tags": [], **fm}
    (vault / f"{name}.md").write_text("---\n" + yaml.safe_dump(full, allow_unicode=True) + "---\n\nbody\n", encoding="utf-8")
    return full


def _fm(path: Path) -> dict:
    return yaml.safe_load(split_frontmatter(path.read_text(encoding="utf-8"))[0])


def _vault(tmp_path: Path) -> Path:
    """A project, an entity with a parenthetical abbreviation, a topic, an
    archived project, and a handful of tagged nodes exercising each rule."""
    v = tmp_path / "vault"; v.mkdir()
    _node(v, "proj", uid="aaaa0001", type="project", title="Loci", status="active")
    _node(v, "ent", uid="aaaa0002", type="entity", title="Globex Corp (GLX)", subtype="organization")
    _node(v, "top", uid="aaaa0003", type="topic", title="User Research", status="active")
    _node(v, "old", uid="aaaa0004", type="project", title="Vela", status="paused", state="archived", archived_at="2026-02-01T00:00:00Z")
    # Two nodes answering to the same name — a topic and a project both called Strategy.
    _node(v, "strat-t", uid="aaaa0005", type="topic", title="Strategy", status="active")
    _node(v, "strat-p", uid="aaaa0006", type="project", title="Strategy", status="active")

    _node(v, "t1", uid="bbbb0001", type="task", title="Ship it", status="todo", subtype="feature",
          tags=["loci", "glx", "user-research", "python"])
    _node(v, "t2", uid="bbbb0002", type="task", title="Already linked", status="todo", subtype="feature",
          tags=["LOCI"], relations=[{"uid": "aaaa0001", "type": "belongs-to"}])
    _node(v, "t3", uid="bbbb0003", type="task", title="Old project", status="todo", subtype="feature",
          tags=["vela", "strategy", "python"])
    _node(v, "d1", uid="bbbb0004", type="document", title="Notes", status="draft", subtype="note",
          tags=["globex-corp", "python"])
    return v


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def test_normalise_folds_case_separators_and_accents():
    assert tag_hygiene.normalise("Acme-Corp") == tag_hygiene.normalise("acmecorp") == "acmecorp"
    assert tag_hygiene.normalise("Айрат") == tag_hygiene.normalise("айрат") != ""
    assert tag_hygiene.normalise("--") == ""


def test_normalise_keeps_the_symbols_that_make_a_name():
    # C, C++ and C# are three topics; R and R&D two entities.
    assert len({tag_hygiene.normalise(n) for n in ("C", "C++", "C#")}) == 3
    assert tag_hygiene.normalise("R&D") != tag_hygiene.normalise("R")
    assert tag_hygiene.normalise("Node.js") == tag_hygiene.normalise("nodejs")  # a dot is still a separator


def test_candidate_names_use_title_stem_and_only_abbreviation_parentheticals():
    assert tag_hygiene.candidate_names({"title": "Globex Corp (GLX)"}) == ["Globex Corp (GLX)", "Globex Corp", "GLX"]
    assert tag_hygiene.candidate_names({"title": "Initech (company)"}) == ["Initech (company)", "Initech"]
    assert tag_hygiene.candidate_names({"title": "Acme Corp", "aliases": ["CM"]}) == ["Acme Corp", "CM"]


def test_candidate_names_ignore_aliases_that_are_not_a_list():
    # `aliases: CM` iterated as a string would answer to `c` and `m`.
    assert tag_hygiene.candidate_names({"title": "Acme Corp", "aliases": "CM"}) == ["Acme Corp"]
    assert tag_hygiene.candidate_names({"title": "Acme Corp", "aliases": None}) == ["Acme Corp"]


def test_candidate_names_treat_proper_noun_and_year_parentheticals_as_glosses():
    # A capital or a digit alone does not make an abbreviation: otherwise every
    # node tagged `acme-corp` would link to the person, not the company.
    assert tag_hygiene.candidate_names({"title": "Jane Doe (Acme Corp)"}) == ["Jane Doe (Acme Corp)", "Jane Doe"]
    assert tag_hygiene.candidate_names({"title": "Initech (French startup)"}) == ["Initech (French startup)", "Initech"]
    assert tag_hygiene.candidate_names({"title": "Offsite (2024)"}) == ["Offsite (2024)", "Offsite"]
    assert tag_hygiene.candidate_names({"title": "Two-factor (2FA)"}) == ["Two-factor (2FA)", "Two-factor", "2FA"]


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def test_plan_picks_the_relation_by_target_type(tmp_path):
    v = _vault(tmp_path)
    plan = mig.plan_vault(v)

    t1 = {(e.tag, e.target.uid, e.relation) for e in plan.edges if e.uid == "bbbb0001"}
    assert t1 == {
        ("loci", "aaaa0001", "belongs-to"),
        ("glx", "aaaa0002", "involves"),
        ("user-research", "aaaa0003", "about"),
    }


def test_plan_drops_but_does_not_double_an_existing_edge(tmp_path):
    plan = mig.plan_vault(_vault(tmp_path))
    [e] = [e for e in plan.edges if e.uid == "bbbb0002"]
    assert e.tag == "LOCI" and e.already_linked
    assert e not in plan.to_add


def test_two_tags_for_one_node_plan_and_write_a_single_edge(tmp_path):
    v = _vault(tmp_path)
    _node(v, "twice", uid="eeee0001", type="task", title="Doubly tagged", status="todo", subtype="feature",
          tags=["loci", "Loci", "glx", "globex-corp"])
    plan = mig.plan_vault(v)

    mine = [e for e in plan.edges if e.uid == "eeee0001"]
    assert [e.tag for e in mine] == ["loci", "Loci", "glx", "globex-corp"]
    assert [(e.tag, e.target.uid) for e in mine if not e.drop_only] == [("loci", "aaaa0001"), ("glx", "aaaa0002")]
    # The report counts nodes, not tag uses: Loci is tagged on t1, t2 and twice.
    [loci_line] = [ln for ln in mig.report(plan, applied=False).splitlines() if "Loci (aaaa0001)" in ln]
    assert "Add 2 belongs-to edge(s)" in loci_line and "from 3 node(s)" in loci_line

    mig.apply_plan(plan)
    fm = _fm(v / "twice.md")
    assert fm["tags"] == []
    assert fm["relations"] == [{"uid": "aaaa0001", "type": "belongs-to"}, {"uid": "aaaa0002", "type": "involves"}]


def test_plan_ignores_archived_targets_and_leaves_ambiguous_tags_alone(tmp_path):
    plan = mig.plan_vault(_vault(tmp_path))
    assert not any(e.target.uid == "aaaa0004" for e in plan.edges)
    assert plan.unmatched["vela"] == 1
    assert set(plan.ambiguous) == {"strategy"}
    assert {t.uid for t in plan.ambiguous["strategy"]} == {"aaaa0005", "aaaa0006"}


def test_plan_counts_tags_that_name_nothing(tmp_path):
    plan = mig.plan_vault(_vault(tmp_path))
    assert plan.unmatched["python"] == 3


def test_plan_counts_and_reports_spellings_of_one_tag_together(tmp_path):
    v = _vault(tmp_path)
    _node(v, "v1", uid="ffff0001", type="task", title="V1", status="todo", subtype="feature", tags=["Python", "Strategy"])
    _node(v, "v2", uid="ffff0002", type="task", title="V2", status="todo", subtype="feature", tags=["Python"])
    plan = mig.plan_vault(v)

    # Five uses under one name, not 3 + 2 that would each sit below the report threshold.
    assert plan.unmatched["python"] == 5 and "Python" not in plan.unmatched
    assert set(plan.ambiguous) == {"strategy"}
    text = mig.report(plan, applied=False)
    assert "#python [also Python](5)" in text
    assert "  #strategy [also Strategy] → " in text


def test_plan_skips_a_node_whose_tags_is_not_a_list(tmp_path):
    v = _vault(tmp_path)
    # `tags: research` read as a string is r, e, s, e, a, r, c, h — and there is an entity called R.
    _node(v, "r", uid="cccc0009", type="entity", title="R", subtype="organization")
    _node(v, "bad", uid="cccc0010", type="task", title="Bad tags", status="todo", subtype="feature", tags="research")
    before = (v / "bad.md").read_text(encoding="utf-8")
    plan = mig.plan_vault(v)

    assert not any(e.uid == "cccc0010" for e in plan.edges)
    assert not any(k in plan.unmatched for k in "research")
    assert plan.problems == ["bad.md: tags is not a list — skipped"]
    assert "bad.md: tags is not a list — skipped" in mig.report(plan, applied=False)

    mig.apply_plan(plan)
    assert (v / "bad.md").read_text(encoding="utf-8") == before


def test_plan_ignores_an_aliases_field_that_is_not_a_list(tmp_path):
    v = _vault(tmp_path)
    _node(v, "cm", uid="cccc0011", type="entity", title="Acme Corp", subtype="organization", aliases="CM")
    _node(v, "c", uid="cccc0012", type="task", title="Tagged c", status="todo", subtype="feature", tags=["c", "cm"])
    plan = mig.plan_vault(v)

    # `c` names nothing; `cm` would have matched a real alias but not a mistyped one.
    assert not any(e.uid == "cccc0012" for e in plan.edges)
    assert plan.unmatched["c"] == 1 and plan.unmatched["cm"] == 1
    assert plan.problems == ["cm.md: aliases is not a list — ignored"]


def test_plan_drops_a_tag_naming_the_node_itself_without_a_self_edge(tmp_path):
    v = _vault(tmp_path)
    _node(v, "selfref", uid="cccc0001", type="topic", title="Ontology", status="active", tags=["ontology"])
    plan = mig.plan_vault(v)
    [e] = [e for e in plan.edges if e.uid == "cccc0001"]
    assert e.already_linked and e.target.uid == "cccc0001"


def test_plan_drops_a_tag_that_repeats_the_nodes_own_type_or_subtype(tmp_path):
    v = _vault(tmp_path)
    # `books` too: the linter's repeats-type rule compares singular forms, and a
    # tag the migration leaves in place is one the linter warns on next.
    _node(v, "bk", uid="dddd0001", type="asset", title="A Book", subtype="book", tags=["book", "Asset", "books", "python"])
    plan = mig.plan_vault(v)

    own = {e.tag for e in plan.edges if e.uid == "dddd0001"}
    assert own == {"book", "Asset", "books"}
    assert all(e.drop_only and e.target is None for e in plan.edges if e.uid == "dddd0001")
    assert plan.unmatched["python"] == 4

    mig.apply_plan(plan)
    assert _fm(v / "bk.md")["tags"] == ["python"]
    assert _fm(v / "bk.md")["relations"] == []


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def test_dry_run_writes_nothing_and_names_the_unmatched(tmp_path):
    v = _vault(tmp_path)
    before = {p.name: p.read_text() for p in v.glob("*.md")}
    plan = mig.plan_vault(v)
    text = mig.report(plan, applied=False)

    assert {p.name: p.read_text() for p in v.glob("*.md")} == before
    assert "Dry run" in text
    assert "#strategy" in text and "Ambiguous" in text
    assert "#python(3)" in text


def test_apply_adds_edges_drops_tags_and_lints_clean(tmp_path):
    v = _vault(tmp_path)
    plan = mig.plan_vault(v)
    written = mig.apply_plan(plan)

    assert written == 3  # t1, t2, d1 — t3's tags matched nothing, so it is untouched
    t1 = _fm(v / "t1.md")
    assert t1["tags"] == ["python"]
    assert t1["relations"] == [
        {"uid": "aaaa0001", "type": "belongs-to"},
        {"uid": "aaaa0002", "type": "involves"},
        {"uid": "aaaa0003", "type": "about"},
    ]
    t2 = _fm(v / "t2.md")
    assert t2["tags"] == [] and t2["relations"] == [{"uid": "aaaa0001", "type": "belongs-to"}]
    t3 = _fm(v / "t3.md")
    assert t3["tags"] == ["vela", "strategy", "python"] and t3["relations"] == []
    d1 = _fm(v / "d1.md")
    assert d1["tags"] == ["python"] and d1["relations"] == [{"uid": "aaaa0002", "type": "involves"}]

    result = lint_vault(v)
    assert result["errors"] == []
    assert mig.plan_vault(v).to_add == []  # idempotent


def test_apply_leaves_the_body_and_bare_timestamps_as_they_were(tmp_path):
    v = _vault(tmp_path)
    # Hand-written frontmatter: bare timestamps (which YAML reads as datetimes)
    # and a body that starts with a blank line, as every vault file does.
    (v / "bare.md").write_text(
        "---\nuid: ffff0001\ntype: task\ntitle: Bare\nstatus: todo\nsubtype: feature\nauthor: self\n"
        "state: active\ncreated_at: 2026-03-04T05:06:07Z\nupdated_at: 2026-03-04T05:06:07Z\narchived_at: null\n"
        "domains: [technology-engineering]\nsummary: s\nreferences: []\nrelations: []\ntags: [loci]\n---\n"
        "\n# Bare\n\nbody\n",
        encoding="utf-8",
    )
    bodies_before = {p.name: split_frontmatter(p.read_text(encoding="utf-8"))[1] for p in v.glob("*.md")}
    mig.apply_plan(mig.plan_vault(v))

    raw = (v / "bare.md").read_text(encoding="utf-8")
    assert "created_at: '2026-03-04T05:06:07Z'" in raw
    assert "+00:00" not in raw
    assert _fm(v / "bare.md")["relations"] == [{"uid": "aaaa0001", "type": "belongs-to"}]
    # Bodies are byte-for-byte what they were — no blank line creeps in after the fence.
    assert {p.name: split_frontmatter(p.read_text(encoding="utf-8"))[1] for p in v.glob("*.md")} == bodies_before


def test_cli_refuses_a_missing_directory(tmp_path):
    assert mig.main([str(tmp_path / "nope")]) == 2
