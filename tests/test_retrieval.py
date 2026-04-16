"""
tests/test_retrieval.py
Phase 1: Retrieval correctness tests.

Tests find_nodes, query_path, query_related, and search_vault against a
static fixture vault. Cases are parametrized from fixtures/expected/retrieval.yaml
so adding a new case requires only a YAML edit — no Python changes.

Assertion modes:
  exact    — result UID set must equal expected_uids exactly
  contains — expected_uids must be a subset of the result UID set
  (path)   — expected_path_uids checked as an ordered list
"""

from pathlib import Path

import pytest
import yaml

YAML_PATH = Path(__file__).parent / "fixtures" / "expected" / "retrieval.yaml"
_cases = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _cases, ids=[c["id"] for c in _cases])
def test_retrieval(loci_api, case):
    method = getattr(loci_api, case["method"])
    result = method(**case["args"])

    if "expected_path_uids" in case:
        # Ordered path assertion
        path_uids = [r["uid"] for r in result]
        assert path_uids == case["expected_path_uids"], (
            f"[{case['id']}] expected path {case['expected_path_uids']}, got {path_uids}"
        )
    else:
        result_uids = {r["uid"] for r in result}
        expected = set(case["expected_uids"])
        if case.get("mode") == "contains":
            assert expected.issubset(result_uids), (
                f"[{case['id']}] expected {expected} ⊆ {result_uids}"
            )
        else:
            assert expected == result_uids, (
                f"[{case['id']}] expected {expected}, got {result_uids}"
            )
