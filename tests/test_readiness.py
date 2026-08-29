"""
tests/test_readiness.py
First-run flow: refusing to work without a vault, and set_vault_root.

The MCP server has no way to prompt the user — it is a subprocess speaking
JSON-RPC. So "not configured yet" has to travel out as a tool error the model
can act on, and the model asks for the path on the server's behalf. These tests
pin that contract: the two error codes, which tools are guarded, and the
guarantee that set_vault_root leaves the very next call working.
"""

import functools
import inspect
from pathlib import Path

import pytest
import yaml

from loci.tools import vault_init
from loci.tools.vault_init import (
    NOT_CONFIGURED,
    VAULT_UNREACHABLE,
    VaultNotReady,
    ensure_ready,
    reset_ready_state,
    set_vault_root,
)

from loci import mcp_server as server


@pytest.fixture(autouse=True)
def clean_readiness():
    """Readiness is a process-wide cache; no test may inherit another's."""
    reset_ready_state()
    server._startup_notice = None
    server._first_ready_work_done = False
    yield
    reset_ready_state()
    server._startup_notice = None
    server._first_ready_work_done = False


@pytest.fixture
def unconfigured(monkeypatch, tmp_path):
    """A Loci that has never been set up: no env override, no config file."""
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)
    monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / "absent" / "config.yml"))


# ---------------------------------------------------------------------------
# ensure_ready
# ---------------------------------------------------------------------------

def test_unconfigured_raises_not_configured(unconfigured):
    with pytest.raises(VaultNotReady) as exc:
        ensure_ready()
    assert exc.value.code == NOT_CONFIGURED


def test_not_configured_message_tells_the_model_to_ask(unconfigured):
    """The whole point of the code: the model must ask, not invent a path."""
    with pytest.raises(VaultNotReady) as exc:
        ensure_ready()
    message = exc.value.message
    assert "set_vault_root" in message
    assert "Do not guess" in message


def test_configured_but_missing_directory_is_unreachable(monkeypatch, tmp_path):
    """A vault on an unmounted drive is a different problem from having none."""
    config = tmp_path / "config.yml"
    config.write_text(yaml.dump({"vault_root": str(tmp_path / "gone")}))
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)
    monkeypatch.setenv("LOCI_CONFIG", str(config))

    with pytest.raises(VaultNotReady) as exc:
        ensure_ready()
    assert exc.value.code == VAULT_UNREACHABLE
    # Never offer to recreate a path the user already chose — that silently
    # starts an empty second vault while the real one is merely offline.
    assert "do not silently create" in exc.value.message.lower()


def test_pinned_missing_vault_blames_the_mount(monkeypatch, tmp_path):
    """Under LOCI_VAULT_ROOT the path is the operator's, so say so."""
    monkeypatch.setenv("LOCI_VAULT_ROOT", str(tmp_path / "not-mounted"))

    with pytest.raises(VaultNotReady) as exc:
        ensure_ready()
    assert exc.value.code == VAULT_UNREACHABLE
    assert "-v " in exc.value.message
    assert "cannot be changed from chat" in exc.value.message


def test_ready_vault_seeds_and_reports_once(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("LOCI_VAULT_ROOT", str(vault))

    first = ensure_ready()
    assert (vault / "meta" / "ontology.yaml").exists()
    assert "seeded" in (first or "")

    # Second call is the hot path in front of every tool: no notice, no work.
    assert ensure_ready() is None


def test_readiness_is_rechecked_when_the_vault_moves(monkeypatch, tmp_path):
    """Caching a bare 'yes' would let the old vault vouch for the new one."""
    first_vault = tmp_path / "one"
    first_vault.mkdir()
    monkeypatch.setenv("LOCI_VAULT_ROOT", str(first_vault))
    ensure_ready()

    monkeypatch.setenv("LOCI_VAULT_ROOT", str(tmp_path / "two-that-is-absent"))
    with pytest.raises(VaultNotReady) as exc:
        ensure_ready()
    assert exc.value.code == VAULT_UNREACHABLE


def test_a_vault_that_cannot_be_seeded_is_only_attempted_once(monkeypatch, tmp_path):
    """
    A read-only mount fails the same way every time. Retrying it in front of
    every tool re-runs the writes and appends the same sentence to the notice
    again, so the user's first list_vault comes back carrying N copies of it.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("LOCI_VAULT_ROOT", str(vault))

    calls = []

    def unwritable():
        calls.append(1)
        raise OSError("Read-only file system")

    monkeypatch.setattr(vault_init, "check_meta_version", unwritable)

    with pytest.raises(OSError):
        ensure_ready()
    for _ in range(3):
        assert ensure_ready() is None  # the failure was already reported

    assert len(calls) == 1


def test_the_failed_seeding_notice_is_not_repeated(monkeypatch, tmp_path):
    """The same failure, seen through the tools the guard fronts."""
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("LOCI_VAULT_ROOT", str(vault))
    monkeypatch.setattr(
        vault_init, "check_meta_version",
        lambda: (_ for _ in ()).throw(OSError("Read-only file system")),
    )
    server._first_ready_work_done = True  # not what this test is about

    for _ in range(4):
        server._check_ready()

    assert server._startup_notice.count("could not be seeded") == 1


def test_a_tilde_in_the_configured_root_is_expanded(monkeypatch, tmp_path):
    """
    prompt_vault_root's own EOF message tells the user to set vault_root by
    hand, so `~/vault` turns up in real configs. Unexpanded, the is_dir() check
    passes against the resolved path and the reseed then targets a literal
    ./~/vault/meta relative to the process cwd.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / "config.yml"
    config.write_text(yaml.dump({"vault_root": "~/vault"}))
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)
    monkeypatch.setenv("LOCI_CONFIG", str(config))
    (tmp_path / "vault" / "meta").mkdir(parents=True)  # a vault due an upgrade

    ensure_ready()

    assert (tmp_path / "vault" / "meta" / "ontology.yaml").exists()
    assert not Path("~").exists(), "reseeded into a literal ~ under the cwd"
    assert yaml.safe_load(config.read_text())["vault_root"] == "~/vault"  # left as written


# ---------------------------------------------------------------------------
# set_vault_root
# ---------------------------------------------------------------------------

def test_set_vault_root_creates_seeds_and_records_in_one_call(unconfigured, tmp_path, monkeypatch):
    """
    The single-pass guarantee. Recording the path now and seeding on next use
    would push a seeding failure onto some later unrelated tool call, where
    neither the user nor the model can make sense of it.
    """
    config = tmp_path / "cfg" / "config.yml"
    monkeypatch.setenv("LOCI_CONFIG", str(config))
    target = tmp_path / "my-notes" / "vault"

    result = set_vault_root(str(target), create=True)

    assert result["vault_root"] == str(target)
    assert result["created"] is True
    assert (target / "meta" / "ontology.yaml").exists()          # seeded
    assert (target / "meta" / vault_init.VERSION_MARKER).exists()  # versioned
    saved = yaml.safe_load(config.read_text())
    assert saved["vault_root"] == str(target)
    assert saved["meta_version"] == vault_init.META_VERSION


def test_the_call_after_set_vault_root_works(unconfigured, tmp_path, monkeypatch):
    """No restart: whatever failed with LOCI_NOT_CONFIGURED can just be retried."""
    monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / "cfg" / "config.yml"))
    with pytest.raises(VaultNotReady):
        ensure_ready()

    set_vault_root(str(tmp_path / "vault"), create=True)

    assert ensure_ready() is None  # ready, and nothing left to report


def test_set_vault_root_keeps_the_rest_of_the_config(unconfigured, tmp_path, monkeypatch):
    """Moving the vault must not silently drop the user's sync settings."""
    config = tmp_path / "config.yml"
    config.write_text(yaml.dump({
        "vault_root": str(tmp_path / "old"),
        "sync_remote": "nextcloud",
        "sync_remote_path": "loci",
        "created_at": "2026-01-01T00:00:00+00:00",
    }))
    monkeypatch.setenv("LOCI_CONFIG", str(config))

    set_vault_root(str(tmp_path / "new"), create=True)

    saved = yaml.safe_load(config.read_text())
    assert saved["vault_root"] == str(tmp_path / "new")
    assert saved["sync_remote"] == "nextcloud"
    assert saved["created_at"] == "2026-01-01T00:00:00+00:00"  # first setup, not this one


def test_set_vault_root_refuses_when_the_deployment_pins_the_root(monkeypatch, tmp_path):
    """
    Docker. Writing to any other path succeeds inside the container and is
    invisible on the host — the data is gone at the next `docker run`.
    """
    monkeypatch.setenv("LOCI_VAULT_ROOT", "/knowledge-vault")

    with pytest.raises(VaultNotReady) as exc:
        set_vault_root(str(tmp_path / "elsewhere"), create=True)
    assert exc.value.code == VAULT_UNREACHABLE
    assert not (tmp_path / "elsewhere").exists()  # nothing created


def test_set_vault_root_will_not_create_without_being_asked(unconfigured, tmp_path):
    target = tmp_path / "does-not-exist"
    with pytest.raises(ValueError, match="create=True"):
        set_vault_root(str(target), create=False)
    assert not target.exists()


def test_create_false_refuses_a_directory_that_is_not_a_vault(unconfigured, tmp_path):
    """
    "Check first" has to mean "write nothing". Probing a path the user half
    remembered must not leave a meta/ skeleton in their photos folder and three
    new directories beside it — least of all while reporting created=False,
    which reads as "an existing vault was adopted".
    """
    photos = tmp_path / "home" / "Photos"
    photos.mkdir(parents=True)
    (photos / "beach.jpg").write_bytes(b"")

    with pytest.raises(ValueError, match="not an existing Loci vault"):
        set_vault_root(str(photos), create=False)

    assert [p.name for p in photos.iterdir()] == ["beach.jpg"]
    assert not (tmp_path / "home" / "assets").exists()
    assert not (tmp_path / "home" / "loci-stage").exists()


def test_create_false_adopts_a_vault_that_is_already_there(unconfigured, tmp_path, monkeypatch):
    """The other half of the contract: an existing vault is what it says yes to."""
    monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / "cfg" / "config.yml"))
    vault = tmp_path / "vault"
    set_vault_root(str(vault), create=True)

    result = set_vault_root(str(vault), create=False)

    assert result["created"] is False
    assert result["vault_root"] == str(vault)


def test_adopting_an_older_vault_upgrades_its_meta_files(unconfigured, tmp_path, monkeypatch):
    """
    A vault synced from another machine can be behind. create_vault_structure
    only writes files that are *missing*, so stamping the current version on it
    without reseeding would record it as up to date while leaving v5 content in
    place — and every later check_meta_version() would then skip it forever.
    """
    config = tmp_path / "cfg" / "config.yml"
    monkeypatch.setenv("LOCI_CONFIG", str(config))
    vault = tmp_path / "vault"
    (vault / "meta").mkdir(parents=True)
    for name in vault_init.META_FILES:
        (vault / "meta" / name).write_text("stale content from v5\n")
    vault_init.write_vault_meta_version(vault, 5)

    set_vault_root(str(vault), create=True)

    ontology = (vault / "meta" / "ontology.yaml").read_text()
    assert ontology == (vault_init.REFERENCES_DIR / "ontology.yaml").read_text()
    assert vault_init.read_vault_meta_version(vault) == vault_init.META_VERSION
    assert ensure_ready() is None  # nothing left for the next call to do


def test_adopting_an_unversioned_complete_vault_keeps_the_users_files(unconfigured, tmp_path, monkeypatch):
    """
    The marker did not always exist, so its absence is not evidence of
    staleness. A vault holding the full canonical set is taken as current —
    reseeding it would overwrite tag-dictionary.md, which the user owns.
    """
    monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / "cfg" / "config.yml"))
    vault = tmp_path / "vault"
    (vault / "meta").mkdir(parents=True)
    for name in vault_init.META_FILES:
        (vault / "meta" / name).write_text(
            (vault_init.REFERENCES_DIR / name).read_text()
        )
    (vault / "meta" / "tag-dictionary.md").write_text("# my own tags\n")

    set_vault_root(str(vault), create=True)

    assert (vault / "meta" / "tag-dictionary.md").read_text() == "# my own tags\n"
    assert vault_init.read_vault_meta_version(vault) == vault_init.META_VERSION


def test_set_vault_root_migrates_a_legacy_config(tmp_path, monkeypatch):
    """
    Moving the vault can be the first thing a pre-#65 install ever does. Reading
    the new config location directly would write a fresh file there, drop the
    sync settings, and strand the legacy one — migrate_legacy_config() returns
    early forever once the destination exists.
    """
    legacy = tmp_path / "checkout" / "config.yml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(yaml.dump({
        "vault_root": str(tmp_path / "old"),
        "sync_remote": "nextcloud",
        "sync_remote_path": "loci",
        "created_at": "2026-01-01T00:00:00+00:00",
    }))
    monkeypatch.setattr(vault_init, "LEGACY_CONFIG_PATH", legacy)
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)
    monkeypatch.delenv("LOCI_CONFIG", raising=False)   # migration is skipped under it
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    set_vault_root(str(tmp_path / "new"), create=True)

    saved = yaml.safe_load((tmp_path / "xdg" / "loci" / "config.yml").read_text())
    assert saved["vault_root"] == str(tmp_path / "new")
    assert saved["sync_remote"] == "nextcloud"
    assert saved["created_at"] == "2026-01-01T00:00:00+00:00"
    assert (legacy.parent / "config.yml.migrated").exists()


def test_set_vault_root_explains_a_config_it_cannot_write(unconfigured, tmp_path, monkeypatch):
    """
    The vault is already on disk by then, so an unwritable ~/.config leaves an
    install that works nowhere and says nothing. A bare OSError escapes the
    tool's ValueError handling and reaches the model as a traceback.
    """
    monkeypatch.setattr(vault_init, "save_config", lambda config: (_ for _ in ()).throw(
        OSError("No space left on device")
    ))

    with pytest.raises(ValueError, match="could not be recorded"):
        set_vault_root(str(tmp_path / "vault"), create=True)


@pytest.mark.parametrize("bad", ["", "   ", "relative/path", "~nosuchuser/vault"])
def test_set_vault_root_rejects_unusable_paths(unconfigured, bad):
    with pytest.raises(ValueError):
        set_vault_root(bad)


def test_set_vault_root_rejects_a_file(unconfigured, tmp_path):
    target = tmp_path / "notes.md"
    target.write_text("not a vault")
    with pytest.raises(ValueError, match="file, not a directory"):
        set_vault_root(str(target))


def test_set_vault_root_expands_a_tilde(unconfigured, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / "cfg" / "config.yml"))

    result = set_vault_root("~/vault", create=True)

    assert result["vault_root"] == str(tmp_path / "vault")
    assert (tmp_path / "vault" / "meta").is_dir()


# ---------------------------------------------------------------------------
# Which tools are guarded
# ---------------------------------------------------------------------------

# Tools that reach nothing but the network, the packaged files, or the random
# number generator. Everything else must refuse until there is a vault.
VAULT_FREE_TOOLS = {
    "generate_uid",        # random hex, no I/O
    "fetch_url_metadata",  # network only
    "read_skill",          # src/loci/skills/<name>/SKILL.md, inside the package
    "write_skill",         # ditto
    "set_vault_root",      # the way out; guarding it would lock the door
    "read_meta",           # guards itself — every key but "config"
}


def _registered_tools():
    """
    The tools as FastMCP holds them, including the exact callable it will
    invoke. Read through the sync tool manager rather than the async
    mcp.list_tools(): under the e2e suite pytest-asyncio already owns the
    event loop, and asyncio.run() inside a test would fail there and nowhere
    else.
    """
    return {t.name: t for t in server.mcp._tool_manager.list_tools()}


def test_every_vault_touching_tool_is_guarded():
    """
    The enforcement mechanism for the rule, so a new tool cannot quietly skip
    it. If this fails on a tool you just added: either it reads or writes the
    vault and wants @requires_vault, or it genuinely does not and belongs in
    VAULT_FREE_TOOLS above.
    """
    unguarded = sorted(
        name for name, tool in _registered_tools().items()
        if name not in VAULT_FREE_TOOLS
        and not getattr(tool.fn, "__loci_guarded__", False)
    )
    assert unguarded == []


def test_the_guard_check_is_not_satisfied_by_any_old_decorator():
    """
    Asserting on functools.wraps' __wrapped__ would pass for a tool wrapped by
    a cache, a timer or an error-mapper — decorated, but not guarded. The
    marker has to come from requires_vault itself.
    """
    @functools.wraps(lambda: None)
    def merely_wrapped():
        return None

    assert hasattr(merely_wrapped, "__wrapped__")
    assert not getattr(merely_wrapped, "__loci_guarded__", False)
    assert getattr(server.search_vault, "__loci_guarded__", False)


def test_vault_free_tools_are_named_by_a_real_tool():
    """Keeps the exemption list from rotting past a rename."""
    assert VAULT_FREE_TOOLS <= set(_registered_tools())


def test_the_guard_does_not_change_the_published_schema():
    """
    FastMCP builds each tool's schema from the signature. A decorator that hid
    it behind (*args, **kwargs) would publish every tool as taking nothing.
    """
    tools = _registered_tools()
    for name in ("find_nodes", "write_vault", "query_recent"):
        published = set(tools[name].parameters.get("properties", {}))
        assert published == set(inspect.signature(getattr(server, name)).parameters)


# ---------------------------------------------------------------------------
# The guard, through the tools
# ---------------------------------------------------------------------------

def test_guarded_tool_refuses_with_the_code(unconfigured):
    with pytest.raises(VaultNotReady) as exc:
        server.search_vault("anything")
    assert exc.value.code == NOT_CONFIGURED
    assert NOT_CONFIGURED in str(exc.value)   # the model reads the message text


def test_vault_free_tools_still_answer_unconfigured(unconfigured):
    """A server with no vault is not a broken server."""
    assert len(server.generate_uid()) == 8
    assert "skill_version" in server.read_skill("loci-save")


def test_read_meta_config_answers_unconfigured(unconfigured):
    """
    The one diagnostic that must survive: it is how the model sees an empty
    vault_root behind the refusal it just got.
    """
    out = server.read_meta("config")
    assert "vault_root:" in out


def test_read_meta_refuses_other_keys_unconfigured(unconfigured):
    """
    Without the guard this answers off the packaged reference copies and looks
    configured — the failure mode the broad guarding exists to prevent.
    """
    with pytest.raises(VaultNotReady) as exc:
        server.read_meta("ontology")
    assert exc.value.code == NOT_CONFIGURED


def test_set_vault_root_tool_unblocks_the_guarded_tools(unconfigured, tmp_path, monkeypatch):
    """End to end: refusal, the model asks, the user answers, work resumes."""
    monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / "cfg" / "config.yml"))
    with pytest.raises(VaultNotReady):
        server.list_vault()

    result = server.set_vault_root(str(tmp_path / "vault"), create=True)
    assert "error" not in result

    assert isinstance(server.list_vault(), dict)


def test_set_vault_root_tool_returns_errors_as_a_dict(unconfigured, tmp_path):
    """An unusable path is the user's typo, not a crash."""
    assert "error" in server.set_vault_root("relative/path")


def test_moving_the_vault_clears_the_previous_vaults_notice(unconfigured, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCI_CONFIG", str(tmp_path / "cfg" / "config.yml"))
    server._startup_notice = "something about the old vault"

    server.set_vault_root(str(tmp_path / "vault"), create=True)

    assert server._startup_notice is None
