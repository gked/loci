# Loci — Claude Instructions

## Project layout

```
app/                        React frontend
  design/                   Design system (tokens, assets, UI kit components)
server/
  api.py                    Public facade used by the MCP server
  loci_mcp/server.py        MCP tool definitions and docstrings
  tools/                    Core business logic (registries, linting, writing)
  skills/
    references/             Canonical meta files seeded to vault/meta/ on init
      ontology.yaml         Type registry source
      relation-dictionary.yaml  Relation registry source
      ontology-user.yaml    User type extensions stub
      relation-dictionary-user.yaml  User relation extensions stub
    loci-save/SKILL.md      Save skill instructions (versioned)
    loci-query/SKILL.md     Query skill instructions (versioned)
  tests/                    Python test suite
    e2e/                    Browser end-to-end suite (Playwright) — see its README.md
    fixtures/vault/         Base fixture vault (unit suite; do not reshape)
    fixtures/e2e-overlay/   Extra nodes layered on top for e2e only
```

## Skill ↔ Tool sync rule

**Always check both directions when touching either side.**

### When modifying Python tools (`server/tools/`, `server/api.py`, `server/loci_mcp/server.py`)

Ask: do the skill files need to reflect this change?

- New MCP tool added → check if any skill should call it and update the relevant SKILL.md
- MCP tool renamed or removed → update every SKILL.md that references it
- `read_meta` file map gains or loses a key → update skill instructions that call `loci__read_meta`
- New registry or validation added → check if skills need to read the new file or follow new rules
- Tool parameter or return shape changes → update skill steps that depend on that shape

### When modifying skill files (`server/skills/`)

Ask: do the Python tools need to reflect this change?

- Skill references a `loci__read_meta` key that doesn't exist in `api.py` → add it
- Skill calls a tool with a parameter that doesn't exist → add or fix the parameter
- Skill describes behaviour (validation, enforcement) that isn't implemented → implement it or note it as aspirational
- Skill version bumped → confirm the vault's copy of the skill also needs updating (user deploys via project update)

### Skill versioning

Skills carry a `skill_version` integer in their frontmatter and in the version-check body line. Bump it whenever instructions change in a way that would alter skill behaviour. Both occurrences must match:

```yaml
---
skill_version: 7   ← frontmatter
---
This skill is at `skill_version: 7`.   ← body check line
```

### Meta file sync

`server/skills/references/` is the source of truth. Files listed in `META_FILES` in `server/tools/vault_init.py` are reseeded to `vault/meta/` on every `META_VERSION` bump. Files in `USER_META_FILES` are seeded once and never overwritten.

When adding a new meta file:
1. Create it in `server/skills/references/`
2. Add it to `META_FILES` or `USER_META_FILES` in `vault_init.py`
3. Bump `META_VERSION`
4. Add the key to the `file_map` in `api.py` → `read_meta()`
5. Update `server.py` docstring for `read_meta`
6. Update any skill that should read the new file

## UI impact check

**Always ask: does this change affect the UI?**

After any code change, check whether the `app/` frontend is affected:

- MCP tool added, renamed, or removed → does the UI call or display results from this tool?
- API response shape changes (new fields, renamed keys, removed fields) → does any React component consume this shape?
- New type, subtype, or relation added to the registry → does the UI render or filter on these values?
- Vault node schema changes (new/removed frontmatter fields) → does the UI read or display those fields?
- Business logic changes (sorting, filtering, validation) → does the UI rely on that behaviour?

If yes: inspect the relevant files under `app/` and update them (or flag to the user that UI changes are needed).

**Then run the e2e suite** (`make test-e2e`) — it is the enforcement mechanism
for this rule. If you changed a component the suite selects on, also update the
selector table in `server/tests/e2e/README.md`.

## Browser e2e suite

`server/tests/e2e/` drives the real app in Chromium against a real uvicorn
backend and a temp vault. **Read `server/tests/e2e/README.md` before touching
it** — it documents four traps that will otherwise cost you an hour (fixture
dates are rewritten per run; many fixture uids 404 on `/api/nodes/{uid}`; the
command palette shows recent nodes until search debounces; expected counts live
only in `vault_facts.py`).

Rules of thumb:

- Selecting on UI state → add a `data-testid`, never match on the Latin display
  text (`praeceptum · command` etc.), and record it in the README's table.
- Adding or removing a fixture node → update `server/tests/e2e/vault_facts.py`;
  `test_fixture_composition.py` fails first and tells you what changed.
- Need a UI state the base fixture vault lacks (archived, ghost, asset) → add a
  node to `server/tests/fixtures/e2e-overlay/`, **not** to `fixtures/vault/`
  (that one backs the unit suite and its counts are asserted on).

## Running tests

```
make test                        # full suite: Python unit + browser e2e
make test-fast                   # unit only (-m "not e2e") — no Node/browser
make test-e2e                    # browser suite only
make e2e-install                 # one-time: download the Chromium binary
uv run pytest server/tests/ -v          # like make test, but skips the npm ci step
uv run pytest server/tests/test_foo.py  # single file
make test-cov                    # with coverage report
```

Tests use `LOCI_VAULT_ROOT` env var (set by the `tmp_vault` fixture in `conftest.py`)
to point registries and api calls at a temporary copy of `server/tests/fixtures/vault/`.

## Registry singleton pattern

`TypeRegistry` and `RelationRegistry` (and any future registry) use a module-level
singleton loaded on first call. Tests that exercise registry-dependent code must
reset the singleton before and after to avoid cross-test pollution:

```python
from type_registry import reset_registry
from relation_registry import reset_relation_registry

@pytest.fixture(autouse=True)
def clean_registries():
    reset_registry()
    reset_relation_registry()
    yield
    reset_registry()
    reset_relation_registry()
```

The `tmp_vault` fixture in `conftest.py` does this for `nx_graph` already — follow
the same pattern when writing tests for any registry-backed module.

## Fixture vault has no `meta/` directory

`server/tests/fixtures/vault/` contains only node files — no `meta/` subdirectory.
This is intentional: registries fall back to `server/skills/references/` when
`vault/meta/<file>` is not found, so tests automatically use the canonical
source files without extra setup.

**Do not add a `meta/` directory to the fixture vault** unless a test specifically
needs to override a registry file. If you do add one, it must be complete — a
partial `meta/` dir will cause the registry to load the partial file instead of
falling back, which silently breaks other tests.

## Adding a new registry

When a new registry is needed (parallel to `TypeRegistry` / `RelationRegistry`):

1. Define the YAML schema in `server/skills/references/<name>.yaml`
2. Create `server/tools/<name>_registry.py` with a `<Name>Registry` class and
   `get_<name>_registry()` / `reset_<name>_registry()` singleton functions,
   mirroring the pattern in `server/tools/relation_registry.py`
3. Add the YAML to `META_FILES` in `vault_init.py` and bump `META_VERSION`
4. Add the `read_meta` key in `api.py` and update the `server.py` docstring
5. Wire validation into `write_file.py` (block on write, warn on patch)
6. Add a lint check in `vault_linter.py`
7. Update any skill that should read or validate against the new registry
8. Add tests: happy path, unknown value blocked, patch warning returned, lint warning emitted
