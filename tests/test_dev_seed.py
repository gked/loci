"""
tests/test_dev_seed.py
The committed dev vault (dev-vault-seed/) and the script that regenerates it.

The seed is what ships; the script is kept so a regeneration after an ontology
change is a command rather than a rewrite. The first test is the rot guard: an
ontology change that invalidates the seed fails here, the same way it would
fail the fixture vault.
"""
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from loci.tools.relation_registry import get_relation_registry
from loci.tools.type_registry import get_registry
from loci.tools.vault_linter import lint_vault

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import dev_seed  # noqa: E402  (must follow sys.path insert)

SEED_DIR = REPO_ROOT / "dev-vault-seed"


def test_the_committed_seed_lints_clean_except_for_its_one_ghost():
    result = lint_vault(SEED_DIR)

    assert result["errors"] == []
    assert [w["code"] for w in result["warnings"]] == ["dangling-relation"], result["warnings"]
    assert len(list(SEED_DIR.glob("*.md"))) == 500


def test_the_seed_is_what_the_script_produces():
    """
    A hand edit to the seed, or a script change without a regeneration, is a
    seed nobody can rebuild. Regenerate with:
        uv run python scripts/dev_seed.py --out dev-vault-seed --force
    """
    generated = dict(dev_seed.Generator(500, 1, 1).build())

    committed = {p.name: p.read_text(encoding="utf-8") for p in SEED_DIR.glob("*.md")}
    assert committed == generated


def test_generated_vocabulary_comes_from_the_registries(tmp_path):
    types = get_registry(None)
    relations = get_relation_registry(None)

    dev_seed.main(["--out", str(tmp_path / "v"), "--n", "60", "--seed", "7", "--ghosts", "0"])
    result = lint_vault(tmp_path / "v")

    assert result["errors"] == []
    assert result["warnings"] == []
    assert set(dev_seed.TYPE_WEIGHTS) <= types.type_names()
    assert all(relations.is_valid(r) for r in dev_seed.RELATION_BY_PAIR.values())
    assert all(relations.is_valid(r) for r in dev_seed.RELATION_BY_SUBTYPE_PAIR.values())


def _built(n: int, seed: int) -> dict[str, dict]:
    gen = dev_seed.Generator(n, seed, 0)
    gen.build()
    return {node["fm"]["uid"]: node["fm"] for node in gen.nodes}


def test_an_event_never_ends_before_it_starts_and_a_log_never_finishes_first():
    """Drawn independently, the pair inverted in ~half the nodes; the UI then
    shows negative durations on the dev data."""
    checked = 0
    for fm in _built(1500, 3).values():
        for later, earlier in dev_seed.PAIRED_DATETIMES.items():
            if later in fm and earlier in fm:
                assert fm[later] > fm[earlier], (fm["type"], fm["title"], earlier, later)
                checked += 1
    assert checked > 20


def test_no_stamp_runs_past_the_span_end():
    """updated_at and archived_at are drawn relative to created_at; uncapped,
    a node created near the span end carried a date months in the future and
    the UI's recent views led with it."""
    gen = dev_seed.Generator(1500, 3, 0)
    gen.build()
    end = gen.stamp(gen.epoch + timedelta(days=gen.span_days))
    checked = 0
    for node in gen.nodes:
        fm = node["fm"]
        for key in ("created_at", "updated_at", "archived_at"):
            if fm.get(key):
                assert fm[key] <= end, (fm["title"], key, fm[key])
                checked += 1
    assert checked > 1500


def test_a_log_never_records_itself():
    """With no asset to point at, the subject is drawn from every node — the
    log included — and a self-link is silently dropped, leaving a log of
    nothing."""
    checked = 0
    for seed in range(100):
        nodes = _built(3, seed)
        for fm in (fm for fm in nodes.values() if fm["type"] == "log"):
            checked += 1
            assert fm["subject_uid"] != fm["uid"], fm["title"]
            assert any(r["uid"] == fm["subject_uid"] for r in fm["relations"])
    assert checked > 1


def test_works_at_only_links_a_person_to_an_organization():
    """The dictionary defines works-at as entity -> organisation; a place that
    works at a place is a wrong label the linter cannot see."""
    nodes = _built(1500, 3)
    seen = set()
    for fm in nodes.values():
        for rel in fm["relations"]:
            target = nodes.get(rel["uid"])
            if fm["type"] == "entity" and target and target["type"] == "entity":
                seen.add((fm["subtype"], target["subtype"], rel["type"]))
    assert seen, "no entity-to-entity edges generated"
    for src, dst, name in seen:
        if name == "works-at":
            assert (src, dst) == ("person", "organization"), (src, dst)
        else:
            assert name == "relates-to", (src, dst, name)
    assert ("person", "organization", "works-at") in seen


def test_the_script_refuses_the_fixtures_directory(tmp_path):
    with pytest.raises(SystemExit, match="refusing"):
        dev_seed.main(["--out", str(REPO_ROOT / "tests" / "fixtures" / "vault")])
    with pytest.raises(SystemExit, match="refusing"):
        dev_seed.main(["--out", str(REPO_ROOT / "tests" / "fixtures" / "anything")])


def test_the_script_refuses_the_configured_vault(tmp_path, monkeypatch):
    """--force unlinks every .md in the target, and the user's notes are not
    in git. The vault Loci is configured to use is never a valid target."""
    vault = tmp_path / "notes"
    vault.mkdir()
    (vault / "mine.md").write_text("keep", encoding="utf-8")

    monkeypatch.setenv("LOCI_VAULT_ROOT", str(vault))
    with pytest.raises(SystemExit, match="configured Loci vault"):
        dev_seed.main(["--out", str(vault), "--force"])
    with pytest.raises(SystemExit, match="configured Loci vault"):
        dev_seed.main(["--out", str(vault / "sub"), "--force"])
    assert (vault / "mine.md").read_text(encoding="utf-8") == "keep"

    monkeypatch.delenv("LOCI_VAULT_ROOT")
    config = tmp_path / "config.yml"
    config.write_text(f"vault_root: {vault}\n", encoding="utf-8")
    monkeypatch.setenv("LOCI_CONFIG", str(config))
    with pytest.raises(SystemExit, match="configured Loci vault"):
        dev_seed.main(["--out", str(vault), "--force"])
    assert (vault / "mine.md").read_text(encoding="utf-8") == "keep"


def test_no_two_entities_share_a_title():
    """api.save refuses an exact title match, so a duplicate person in the seed
    makes that name unsaveable in the dev vault. 1500 nodes outgrows every
    pool, so the recombination fallback is exercised too."""
    for n in (500, 1500):
        titles = [fm["title"] for fm in _built(n, 3).values() if fm["type"] == "entity"]
        assert len(titles) == len(set(titles)), sorted(t for t in titles if titles.count(t) > 1)
    assert len(titles) > len(dev_seed.PEOPLE) + len(dev_seed.ORGS) + len(dev_seed.PLACES)


def test_the_script_refuses_a_target_that_is_a_file(tmp_path):
    out = tmp_path / "vault.md"
    out.write_text("not a directory", encoding="utf-8")

    with pytest.raises(SystemExit, match="is a file"):
        dev_seed.main(["--out", str(out), "--n", "5"])
    assert out.read_text(encoding="utf-8") == "not a directory"


def test_the_script_refuses_fewer_than_two_nodes(tmp_path, capsys):
    """One node becomes the hub, and the orphan fallback picks from an empty
    list of others."""
    with pytest.raises(SystemExit):
        dev_seed.main(["--out", str(tmp_path / "v"), "--n", "1"])
    assert "--n must be at least 2" in capsys.readouterr().err
    assert not (tmp_path / "v").exists()

    dev_seed.main(["--out", str(tmp_path / "w"), "--n", "2"])
    assert len(list((tmp_path / "w").glob("*.md"))) == 2


def test_the_script_refuses_a_non_empty_target_without_force(tmp_path):
    out = tmp_path / "v"
    out.mkdir()
    (out / "mine.md").write_text("keep", encoding="utf-8")

    with pytest.raises(SystemExit, match="--force"):
        dev_seed.main(["--out", str(out), "--n", "5"])
    assert (out / "mine.md").exists()

    dev_seed.main(["--out", str(out), "--n", "5", "--force"])
    assert not (out / "mine.md").exists()
    assert len(list(out.glob("*.md"))) == 5
