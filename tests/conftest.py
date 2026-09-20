"""
tests/conftest.py
Shared fixtures for the Loci test suite.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"

# Set at conftest import — before any test module is imported, and so before
# loci/mcp_server.py runs check_meta_version() at *its* import. A fixture is too
# late for that: collection would already have read the developer's real
# ~/.config/loci/config.yml and migrated a project-root config.yml out from
# under them. Subprocesses the e2e suite spawns inherit this too.
#
# test_vault_init.py guards this line: it captures LOCI_CONFIG at *its* import,
# which happens after this and before the isolated_config fixture below, so
# deleting the assignment fails the suite rather than silently migrating.
os.environ["LOCI_CONFIG"] = str(
    Path(tempfile.mkdtemp(prefix="loci-test-config-")) / "config.yml"
)

from loci.tools import nx_graph as _nx_graph  # noqa: E402  (must follow the LOCI_CONFIG assignment above)
from loci.tools.type_registry import reset_registry as _reset_type_registry  # noqa: E402
from loci.tools.relation_registry import reset_relation_registry as _reset_relation_registry  # noqa: E402
from loci.tools.scheme_registry import reset_scheme_registry as _reset_scheme_registry  # noqa: E402
from loci.tools.vault_init import reset_ready_state as _reset_ready_state  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_config(tmp_path_factory, monkeypatch):
    """
    Give each test its own throwaway config file.

    The module-level LOCI_CONFIG above already keeps the suite off the real one;
    this narrows it further so a test that writes config (the API token, a
    save_config call) cannot be seen by the next one. Setting LOCI_CONFIG also
    suppresses migrate_legacy_config(), which is what keeps the developer's
    project-root config.yml untouched.

    Tests that exercise resolution or migration override LOCI_CONFIG themselves.
    """
    config = tmp_path_factory.mktemp("loci-config") / "config.yml"
    monkeypatch.setenv("LOCI_CONFIG", str(config))
    yield config


@pytest.fixture(autouse=True)
def no_inherited_git_env(monkeypatch):
    """
    Keep every git a test runs inside the test's own directory.

    git exports GIT_DIR to a hook fired from a linked worktree, and the
    pre-push hook runs this suite. A test that shells out to git — to build a
    throwaway repo in tmp_path, or through release_notes — inherits it, and
    every one of its commands then acts on the real repository: that once
    marked the checkout bare and committed fixture files onto the branch
    being pushed. Dropping the whole GIT_* family here means no test has to
    remember to.
    """
    for name in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(name)


@pytest.fixture
def tmp_vault(tmp_path):
    """
    Copy the static fixture vault to a fresh temp directory.
    Sets LOCI_VAULT_ROOT so api.py and nx_graph pick up the right root.
    Resets the graph singleton before and after so each test gets a clean build.

    Readiness is reset alongside them: ensure_ready() caches the root it last
    verified, and every test here gets a different one, so a stale cache would
    let one test's vault vouch for the next test's.
    """
    vault_path = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault_path)
    os.environ["LOCI_VAULT_ROOT"] = str(vault_path)

    _nx_graph._graph = None   # force rebuild from the temp vault
    _nx_graph._built_at = 0.0
    _reset_type_registry()
    _reset_relation_registry()
    _reset_scheme_registry()
    _reset_ready_state()

    yield vault_path

    del os.environ["LOCI_VAULT_ROOT"]
    _nx_graph._graph = None
    _nx_graph._built_at = 0.0
    _reset_type_registry()
    _reset_relation_registry()
    _reset_scheme_registry()
    _reset_ready_state()


@pytest.fixture
def loci_api(tmp_vault):
    """
    Return a thin wrapper object with MCP-compatible method signatures,
    backed by nx_graph functions acting on the tmp_vault.
    """
    _nx_graph.get(tmp_vault)  # eagerly build the graph from the temp vault

    class _API:
        @staticmethod
        def find_nodes(
            type=None,
            tag=None,
            status=None,
            due_before=None,
            due_after=None,
            created_after=None,
            updated_after=None,
            related_to=None,
            language=None,
        ):
            return _nx_graph.find(
                node_type=type,
                tag=tag,
                status=status,
                due_before=due_before,
                due_after=due_after,
                created_after=created_after,
                updated_after=updated_after,
                related_to=related_to,
                language=language,
            )

        @staticmethod
        def query_related(uid, depth=2):
            return _nx_graph.related(uid, depth)

        @staticmethod
        def query_path(uid_from, uid_to):
            return _nx_graph.path(uid_from, uid_to)

        @staticmethod
        def search_vault(query):
            return _nx_graph.search(query)

    return _API()
