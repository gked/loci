# Loci — Claude Instructions

## Project layout

```
api.py                      Public facade used by the MCP server
loci_mcp/server.py          MCP tool definitions and docstrings
tools/                      Core business logic (registries, linting, writing)
loci-skill/
  references/               Canonical meta files seeded to vault/meta/ on init
    ontology.yaml           Type registry source
    relation-dictionary.yaml  Relation registry source
    ontology-user.yaml      User type extensions stub
    relation-dictionary-user.yaml  User relation extensions stub
  loci-save/SKILL.md        Save skill instructions (versioned)
  loci-query/SKILL.md       Query skill instructions (versioned)
```

## Skill ↔ Tool sync rule

**Always check both directions when touching either side.**

### When modifying Python tools (`tools/`, `api.py`, `loci_mcp/server.py`)

Ask: do the skill files need to reflect this change?

- New MCP tool added → check if any skill should call it and update the relevant SKILL.md
- MCP tool renamed or removed → update every SKILL.md that references it
- `read_meta` file map gains or loses a key → update skill instructions that call `loci__read_meta`
- New registry or validation added → check if skills need to read the new file or follow new rules
- Tool parameter or return shape changes → update skill steps that depend on that shape

### When modifying skill files (`loci-skill/`)

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

`loci-skill/references/` is the source of truth. Files listed in `META_FILES` in `tools/vault_init.py` are reseeded to `vault/meta/` on every `META_VERSION` bump. Files in `USER_META_FILES` are seeded once and never overwritten.

When adding a new meta file:
1. Create it in `loci-skill/references/`
2. Add it to `META_FILES` or `USER_META_FILES` in `vault_init.py`
3. Bump `META_VERSION`
4. Add the key to the `file_map` in `api.py` → `read_meta()`
5. Update `server.py` docstring for `read_meta`
6. Update any skill that should read the new file

## Running tests

```
make test                        # install dev deps + run full suite
uv run pytest tests/ -v          # same, verbose
uv run pytest tests/test_foo.py  # single file
make test-cov                    # with coverage report
```

Tests use `LOCI_VAULT_ROOT` env var (set by the `tmp_vault` fixture in `conftest.py`)
to point registries and api calls at a temporary copy of `tests/fixtures/vault/`.

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

`tests/fixtures/vault/` contains only node files — no `meta/` subdirectory.
This is intentional: registries fall back to `loci-skill/references/` when
`vault/meta/<file>` is not found, so tests automatically use the canonical
source files without extra setup.

**Do not add a `meta/` directory to the fixture vault** unless a test specifically
needs to override a registry file. If you do add one, it must be complete — a
partial `meta/` dir will cause the registry to load the partial file instead of
falling back, which silently breaks other tests.

## Adding a new registry

When a new registry is needed (parallel to `TypeRegistry` / `RelationRegistry`):

1. Define the YAML schema in `loci-skill/references/<name>.yaml`
2. Create `tools/<name>_registry.py` with a `<Name>Registry` class and
   `get_<name>_registry()` / `reset_<name>_registry()` singleton functions,
   mirroring the pattern in `tools/relation_registry.py`
3. Add the YAML to `META_FILES` in `vault_init.py` and bump `META_VERSION`
4. Add the `read_meta` key in `api.py` and update the `server.py` docstring
5. Wire validation into `write_file.py` (block on write, warn on patch)
6. Add a lint check in `vault_linter.py`
7. Update any skill that should read or validate against the new registry
8. Add tests: happy path, unknown value blocked, patch warning returned, lint warning emitted
