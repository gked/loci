"""
tests/conftest.py
Shared fixtures for the Loci test suite.
"""

import os
import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"

# Put tools/ on sys.path so nx_graph can be imported directly.
# api.py does the same at import time; doing it here ensures the module
# is available before any test file imports api.
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import nx_graph as _nx_graph  # noqa: E402  (must follow sys.path insert)


@pytest.fixture
def tmp_vault(tmp_path):
    """
    Copy the static fixture vault to a fresh temp directory.
    Sets LOCI_VAULT_ROOT so api.py and nx_graph pick up the right root.
    Resets the graph singleton before and after so each test gets a clean build.
    """
    vault_path = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault_path)
    os.environ["LOCI_VAULT_ROOT"] = str(vault_path)

    _nx_graph._graph = None  # force rebuild from the temp vault

    yield vault_path

    del os.environ["LOCI_VAULT_ROOT"]
    _nx_graph._graph = None  # clean up so the next test starts fresh


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
