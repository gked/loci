# Testing

## Overview

Loci has two test suites:

- **The unit suite** (`tests/test_*.py`) runs pytest against a static fixture
  vault. It needs no MCP server, no Node, and no browser.
- **The browser e2e suite** (`tests/e2e/`) runs Playwright in Chromium against
  the real React app, a real FastAPI backend, and a temporary vault. Read
  [tests/e2e/README.md](../tests/e2e/README.md) before you change it.

CI runs both suites on every push and pull request. Both are required checks
on `main`.

Every change carries a test. The rules are in [CLAUDE.md](../CLAUDE.md#branch-and-pr-rules)
and [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Running tests locally

```bash
make e2e-install    # one time: download the Chromium binary
make test           # both suites
make test-fast      # unit suite only (-m "not e2e"), no Node or browser
make test-e2e       # browser suite only
make test-cov       # unit suite with a coverage report in the terminal
make cov-html       # unit suite with an HTML coverage report in htmlcov/
```

`make test` runs `uv sync --extra dev` and `npm ci --prefix app` first, then
`uv run pytest tests/`. `uv run` uses the project's `.venv`, so you do not
need to activate it.

`htmlcov/` is a local build product. It is not committed.

---

## The unit suite

```
tests/
  conftest.py                     ← shared fixtures (tmp_vault, loci_api)
  test_*.py                       ← one file per module or concern
  fixtures/
    vault/                        ← static fixture vault (node files only, no meta/)
    expected/
      retrieval.yaml              ← retrieval cases: method, args, expected UIDs
```

The files cover the registries and validation (`test_type_registry.py`,
`test_relation_registry.py`, `test_scheme_registry.py`, `test_write_file.py`,
`test_vault_linter.py`), the graph and retrieval (`test_nx_graph.py`,
`test_retrieval.py`), assets and the inbox, the MCP and HTTP servers, vault
history, skills and their install (`test_skill_files.py`,
`test_skills_install.py`, `test_skill_assembly.py`), and the packaging and
release tooling (`test_publishing.py`, `test_release.py`).

Some tests guard the docs too. For example, `test_publishing.py` requires
absolute links in the README, because PyPI shows the README out of context,
and `test_skill_files.py` fails if a removed command still appears in any
`.md` or `.py` file.

### `tmp_vault` fixture

Copies the static fixture vault to a temp directory, sets `LOCI_VAULT_ROOT`,
and resets the `nx_graph` singleton. Each test gets a clean graph. Tests for
registry-backed code also reset the registry singletons; see
[CLAUDE.md](../CLAUDE.md#registry-singleton-pattern).

### `loci_api` fixture

A thin wrapper with MCP-compatible method signatures (`find_nodes`,
`query_related`, `query_path`, `search_vault`) backed by `nx_graph` functions.
Tests call the same API shape as the MCP tools, without the server layer.

### Adding a retrieval case

Most retrieval cases need only YAML. Add an entry to
`tests/fixtures/expected/retrieval.yaml`:

```yaml
- id: find_nodes_by_tag_ml
  method: find_nodes
  args: {tag: ml}
  expected_uids: [ccc00001, ccc00002]
  mode: exact
```

| mode | behaviour |
|------|-----------|
| `exact` | the result UID set must equal `expected_uids` |
| `contains` | `expected_uids` must be a subset of the result set |
| *(omitted)* | path test: checks `expected_path_uids` as an ordered list |

If the case needs a node that does not exist, add a Markdown file to
`tests/fixtures/vault/`.

### The fixture vault

`tests/fixtures/vault/` is a small, fixed set of nodes for exact assertions:
tasks, articles, documents, topics, and entities; a hub-and-spoke topology
(`query_related` depth); linear chains (`query_path`); language variants; due
dates; and searchable titles and summaries.

Do not store real content in it. Do not add a `meta/` folder to it: the
registries fall back to `src/loci/skills/references/` when `meta/` is absent.
Nodes that only the e2e suite needs go in `tests/fixtures/e2e-overlay/`.

---

## The browser e2e suite

See [tests/e2e/README.md](../tests/e2e/README.md). It covers how a run starts
the servers, the fixture overlay, the `data-testid` selector table, and four
traps that will otherwise cost you time.

---

## CI

`.github/workflows/test.yml` has two jobs:

| Job | Runs |
|---|---|
| `Python unit tests` | `uv run pytest tests/ -v -m "not e2e"` |
| `Browser e2e tests` | Installs Chromium, builds the app, runs `tests/e2e/` |

Both are required status checks on `main`, together with `cla`.
