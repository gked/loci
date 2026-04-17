# Testing

## Overview

Loci uses pytest with a static fixture vault. Tests run against a deterministic in-memory graph — no live vault, no MCP server required.

CI runs on every push and pull request via GitHub Actions.

---

## Running tests locally

```bash
make test
```

This runs two steps in sequence:

- `uv sync --extra dev` — installs the packages listed under `[project.optional-dependencies] dev` in `pyproject.toml` (pytest, pytest-cov) into the project's `.venv`. Only needed once, or after adding new dependencies.
- `uv run pytest tests/ -v` — runs pytest inside the `.venv` without activating it manually. `uv run` ensures the venv is used regardless of which Python is active in your shell.

To run with coverage reporting — which shows which lines in `tools/`, `api.py`, and `loci_mcp/` were not exercised by any test:

```bash
make test-cov
```

To generate an HTML coverage report and open it in the browser:

```bash
make cov-html
```

The report is written to `htmlcov/index.html`. It is committed alongside the tests so the latest coverage snapshot is always available without re-running the suite.

---

## Structure

```
tests/
  conftest.py                     ← shared fixtures (tmp_vault, loci_api)
  test_retrieval.py               ← parametrized retrieval correctness tests
  fixtures/
    vault/                        ← static fixture vault (markdown nodes)
    expected/
      retrieval.yaml              ← test cases: method, args, expected UIDs
```

### `tmp_vault` fixture

Copies the static fixture vault to a temp directory, sets `LOCI_VAULT_ROOT`, and resets the `nx_graph` singleton. Each test gets a clean graph — no state leaks between tests.

### `loci_api` fixture

A thin wrapper with MCP-compatible method signatures (`find_nodes`, `query_related`, `query_path`, `search_vault`) backed by `nx_graph` functions. Tests call the same API shape as the MCP tools, but without the server layer.

---

## Adding test cases

Most cases only require editing YAML — no Python changes needed.

Open `tests/fixtures/expected/retrieval.yaml` and add an entry:

```yaml
- id: find_nodes_by_tag_ml
  method: find_nodes
  args: {tag: ml}
  expected_uids: [ccc00001, ccc00002]
  mode: exact
```

**Assertion modes:**

| mode | behavior |
|------|----------|
| `exact` | result UID set must equal `expected_uids` exactly |
| `contains` | `expected_uids` must be a subset of the result set |
| *(omitted)* | path test — checks `expected_path_uids` as an ordered list |

If the new case requires a fixture node that doesn't exist yet, add a markdown file to `tests/fixtures/vault/` with the appropriate frontmatter (uid, type, tags, relations, etc.).

---

## Fixture vault

The fixture vault in `tests/fixtures/vault/` is a self-contained set of nodes designed for deterministic assertions. It covers:

- Tasks, articles, documents, topics, entities
- Hub-and-spoke topology (for `query_related` depth tests)
- Linear chains (for `query_path` tests)
- Language variants (for `language` filter tests)
- Due-date nodes (for date filter tests)
- Nodes with searchable titles and summaries (for `search_vault` tests)

Do not use this vault to store real content. It exists solely to support tests.

---

## CI

Tests run on every push and pull request:

```yaml
# .github/workflows/test.yml
- run: uv sync --extra dev
- run: uv run pytest tests/ -v
```
