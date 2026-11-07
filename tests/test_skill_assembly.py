"""
tests/test_skill_assembly.py
How read_skill and write_skill put a skill together: the packaged procedure
plus the user's additions from vault/skills/<skill>.md.

The design this replaces kept a full copy of every skill in ~/.claude/skills/
with a version check at the top, and that copy ran on its own whenever the
numbers matched — so nothing composed on the server side ever reached the
model. What these tests hold in place is the other half of the stub: that the
server really does append the user's file, says how the two halves combine,
and never lets write_skill touch the packaged procedure.
"""

from pathlib import Path

import pytest

from loci import api, skill_assembly
from loci.tools.vault_init import REFERENCES_DIR

SKILLS = ["loci-save", "loci-query", "loci-inbox", "loci-ingest-directory"]


def _overlay(tmp_vault, skill="loci-save") -> Path:
    return skill_assembly.overlay_path(tmp_vault, skill)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def test_split_frontmatter_keeps_the_fences_on_the_frontmatter():
    fm, body = skill_assembly.split_frontmatter("---\nname: x\n---\nbody\n")

    assert fm == "---\nname: x\n---\n"
    assert body == "body\n"


def test_split_frontmatter_with_none_is_all_body():
    assert skill_assembly.split_frontmatter("just text\n") == ("", "just text\n")
    assert skill_assembly.split_frontmatter("---\nunterminated\n") == ("", "---\nunterminated\n")


# ---------------------------------------------------------------------------
# read_skill
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", SKILLS)
def test_read_skill_returns_procedure_then_additions(tmp_vault, skill):
    out = api.read_skill(skill)

    procedure = skill_assembly.split_frontmatter(
        skill_assembly.canonical_path(skill).read_text()
    )[1].strip()
    assert procedure in out
    assert out.index(procedure) < out.index(f"# {skill_assembly.OVERLAY_HEADING}")


def test_read_skill_strips_the_frontmatter():
    """The frontmatter is Claude Code's trigger metadata, already in the stub;
    in the assembled document it is noise ahead of the preamble."""
    out = api.read_skill("loci-save")

    assert not out.startswith("---")
    assert "description: >" not in out


def test_read_skill_appends_the_vault_overlay(tmp_vault):
    _overlay(tmp_vault).parent.mkdir()
    _overlay(tmp_vault).write_text("# mine\n\n- Always tag meeting notes #meeting.\n")

    out = api.read_skill("loci-save")

    assert "Always tag meeting notes #meeting." in out
    assert out.rstrip().endswith("Always tag meeting notes #meeting.")


def test_read_skill_falls_back_to_the_seed_when_the_vault_has_no_overlay(tmp_vault):
    """The fixture vault has no meta/ at all — the shape of every vault seeded
    before the overlays existed. Falling back to the packaged seed matches what
    read_meta does, so the model still gets the seed's header to append under."""
    assert not _overlay(tmp_vault).exists()

    out = api.read_skill("loci-save")

    seed = (REFERENCES_DIR / "loci-save-user.md").read_text().strip()
    assert seed in out


def test_read_skill_labels_the_seed_fallback_as_not_the_vault_file(tmp_vault):
    """A vault whose meta/ is missing looks identical to one that has never
    been seeded — a sync folder that remounted as an empty placeholder, say. The
    seed must not be presented as the user's file, or the model reports "no
    rules" and an append lands in the placeholder, colliding with the real file
    when it comes back."""
    assert not _overlay(tmp_vault).exists()

    out = api.read_skill("loci-save")
    heading = next(l for l in out.splitlines() if l.startswith(f"# {skill_assembly.OVERLAY_HEADING}"))

    assert "packaged default" in heading
    assert "not in the vault yet" in heading
    assert "could not be loaded" in heading


def test_read_skill_labels_a_real_overlay_as_the_vault_file(tmp_vault):
    _overlay(tmp_vault).parent.mkdir()
    _overlay(tmp_vault).write_text("# mine\n")

    out = api.read_skill("loci-save")
    heading = next(l for l in out.splitlines() if l.startswith(f"# {skill_assembly.OVERLAY_HEADING}"))

    assert heading == f"# {skill_assembly.OVERLAY_HEADING} (`vault/skills/loci-save.md`)"
    assert "packaged default" not in out


def test_read_skill_never_names_a_pre_v14_overlay_path(tmp_vault):
    """The preamble and the "Your additions" heading both tell the model where
    the user's rules live, and they have to agree. A preamble built from the old
    directory and the new filename names a file that has existed under neither
    layout, and it is the first thing the model reads."""
    out = api.read_skill("loci-save")

    assert "vault/meta/" not in out
    assert out.split("---", 1)[0].count(skill_assembly.overlay_display("loci-save")) == 1


def test_read_skill_names_the_override_rule_and_the_lock(tmp_vault):
    """The preamble is the contract: user wins, except under 🔒. Both halves
    have to be stated, and the marker in the preamble has to be the one the
    procedures actually use."""
    out = api.read_skill("loci-save")
    preamble = out.split("---", 1)[0]

    assert "additions win" in preamble
    assert skill_assembly.PROTECTED in preamble
    assert f"## {skill_assembly.PROTECTED} Ground rule" in out


def test_read_skill_points_at_write_skill_with_the_right_name(tmp_vault):
    out = api.read_skill("loci-query")

    assert 'loci__write_skill(skill="loci-query"' in out


def test_read_skill_warns_that_content_replaces_and_names_append(tmp_vault):
    """The preamble is the only document the model is sure to have in front of
    it when the user says "from now on, ...". If it does not say that `content`
    replaces the file, the natural call wipes every rule already there."""
    preamble = api.read_skill("loci-save").split("---", 1)[0]

    assert "replaces" in preamble
    assert "append=True" in preamble


def test_read_skill_unknown_skill_raises(tmp_vault):
    with pytest.raises(FileNotFoundError):
        api.read_skill("loci-does-not-exist")


def test_read_skill_without_a_vault_says_so(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)
    monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / "absent" / "config.yml"))

    out = api.read_skill("loci-save")

    assert "Ground rule" in out
    assert "No vault is configured yet" in out


# ---------------------------------------------------------------------------
# write_skill
# ---------------------------------------------------------------------------

def test_write_skill_writes_the_overlay_and_only_the_overlay(tmp_vault):
    canonical = skill_assembly.canonical_path("loci-save")
    before = canonical.read_text()

    path = api.write_skill("# mine\n\n- rule one\n", "loci-save")

    assert Path(path) == _overlay(tmp_vault)
    assert _overlay(tmp_vault).read_text() == "# mine\n\n- rule one\n"
    assert canonical.read_text() == before


def test_write_skill_is_visible_on_the_next_read(tmp_vault):
    api.write_skill("- rule one\n", "loci-save")

    assert "- rule one" in api.read_skill("loci-save")


def test_write_skill_creates_meta_if_missing(tmp_vault):
    assert not (tmp_vault / "meta").exists()

    api.write_skill("- rule one\n", "loci-inbox")

    assert _overlay(tmp_vault, "loci-inbox").read_text() == "- rule one\n"


def test_write_skill_replaces_by_default(tmp_vault):
    api.write_skill("- rule one\n", "loci-save")
    api.write_skill("- rule two\n", "loci-save")

    assert _overlay(tmp_vault).read_text() == "- rule two\n"


def test_write_skill_append_keeps_what_was_there(tmp_vault):
    api.write_skill("- rule one", "loci-save")
    api.write_skill("- rule two\n", "loci-save", append=True)

    assert _overlay(tmp_vault).read_text() == "- rule one\n\n- rule two\n"


def test_write_skill_append_to_an_unseeded_vault_starts_from_the_seed(tmp_vault):
    """An append is "add a rule", and on a vault that predates the overlay the
    only place for it is under the seed's header — not a bare file that loses
    the explanation of what the file is for."""
    api.write_skill("- rule one\n", "loci-save", append=True)

    text = _overlay(tmp_vault).read_text()
    assert text.startswith("# loci-save — your additions")
    assert text.rstrip().endswith("- rule one")


def test_write_skill_unknown_skill_raises_and_writes_nothing(tmp_vault):
    with pytest.raises(FileNotFoundError):
        api.write_skill("- rule\n", "loci-does-not-exist")

    assert not (tmp_vault / "meta").exists()


# ---------------------------------------------------------------------------
# The seeds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", SKILLS)
def test_overlay_seed_carries_no_rules(skill):
    """The seed is appended to the skill verbatim, so anything instruction-
    shaped in it is a rule the user never wrote. Explanation and an empty
    section, nothing else — examples belong in the docs."""
    seed = (REFERENCES_DIR / skill_assembly.seed_filename(skill)).read_text()

    rules = seed.split("## Rules", 1)[1].strip()
    assert rules == "_None yet._"
    assert skill in seed
    assert skill_assembly.PROTECTED in seed


def test_preamble_says_tool_names_vary_by_client():
    """Procedures write `loci__x`; Hermes shows `mcp_loci_x`, Claude `mcp__loci__x`.
    The preamble is where the model learns they are the same tools."""
    preamble = api.read_skill("loci-save").split("---", 1)[0]

    assert "mcp_loci_<tool>" in preamble
    assert "mcp__loci__<tool>" in preamble
