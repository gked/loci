# The Loci Ontology System — Developer Guide

Orientation doc for anyone touching types, relations, or schemes. It explains
how the pieces fit together and where the sharp edges are. Every other file in
this directory is *content* (vocabulary, guidance); this one is *documentation
about the machinery*.

> **This file is not seeded to vaults.** It is deliberately absent from
> `META_FILES` / `USER_META_FILES` in `src/loci/tools/vault_init.py` and from the
> `read_meta` file map in `src/loci/api.py`. It is a developer doc that lives with
> the source, not a runtime meta file. Don't "fix" that by adding it.

---

## 1. What the ontology system is

> **Two words that are not the same thing.** The user guide groups the types
> into four *kinds* (object, information, occurrent, concept). Kinds live in
> prose only — no registry reads them — and the word is `kind`.
> `relation-dictionary.yaml` has a `group:` key on every relation, and that
> one *is* loaded and stored, but nothing acts on it: it carries no rules.
> Don't "harmonise" the two names; they differ because one
> is a design-time idea and the other is a cosmetic label.

Loci stores knowledge as markdown files with YAML frontmatter. The ontology
system is what makes that frontmatter *mean* something: it defines which node
types exist, which fields each type requires, which values enum fields may hold,
which edge labels are legal between nodes, and which location schemes an asset
may point at.

It is made of **three registries**, each built from the same pattern:

| Registry | Class | Module | Governs |
|---|---|---|---|
| Types | `TypeRegistry` | `src/loci/tools/type_registry.py` | node `type`, its fields, enum values, subtypes |
| Relations | `RelationRegistry` | `src/loci/tools/relation_registry.py` | the `type` on each entry in `relations:` |
| Schemes | `SchemeRegistry` | `src/loci/tools/scheme_registry.py` | `scheme` on each `has_asset[].locations[]` |

Everything else — the `.md` files in this directory — is *guidance for the LLM*,
not enforcement. The YAML files are the enforceable contract.

**Structural authority rule:** if a `.md` file in this directory disagrees with
the corresponding `.yaml`, the YAML wins. The `.md` files say *when* to use a
type; the YAML says *what a type is*. Never encode required fields or enum
values only in prose.

---

## 2. File inventory

All source files live in `src/loci/skills/references/` — this directory is the
source of truth. Copies under `<vault>/meta/` are derived.

| File | Kind | Reseeded? | Read by |
|---|---|---|---|
| `ontology.yaml` | machine | yes, on `META_VERSION` bump | `TypeRegistry` |
| `ontology-user.yaml` | machine | **never** (user owns it) | `TypeRegistry` |
| `relation-dictionary.yaml` | machine | yes | `RelationRegistry` |
| `relation-dictionary-user.yaml` | machine | **never** | `RelationRegistry` |
| `scheme-dictionary.yaml` | machine | yes | `SchemeRegistry` |
| `scheme-dictionary-user.yaml` | machine | **never** | `SchemeRegistry` |
| `type-dictionary.md` | guidance | yes | LLM via `read_meta` |
| `type-decision.md` | guidance | **not wired** — see §8 | nothing |
| `field-dictionary.md` | guidance | yes | LLM via `read_meta` |
| `relation-dictionary.md` | guidance | yes | LLM via `read_meta` |
| `tag-dictionary.md` | guidance | no — user-appendable via `write_meta` | LLM via `read_meta` |
| `foreign-definitions.md` | guidance | no — appended at runtime | LLM via `read_meta` |
| `ontology-guide.md` | user prose | yes | the user, in their vault; LLM via `read_meta` |
| `ontology-system.md` | dev doc | no | humans / agents reading the repo |

`META_FILES` is overwritten wholesale on every `META_VERSION` bump.
`USER_META_FILES` is copied once at init and never touched again — that is the
only reason user extensions survive upgrades. Putting a file in the wrong list
either freezes canonical vocabulary or destroys user data. The test is simple:
if anything can write the file after seeding — `api.write_meta` accepts it, or
a skill appends to it — it belongs in `USER_META_FILES`. That is why
`tag-dictionary.md` and `foreign-definitions.md` live there despite being
canonical in origin.

---

## 3. Canonical vs. user layer

Each registry loads two files: a canonical one you control, and a user one the
vault owner controls. The user layer is **additive only**, and the safety rules
are enforced at load time — a bad user entry is skipped with a warning on
`registry.warnings`, and the server keeps running with whatever was valid. A
malformed user file must never take the vault down.

**Types** (`TypeRegistry._load_user`, and the same rules re-implemented for
pre-write checking in `validate_user_type`):

1. `extends` must name a **canonical** type — no new roots, no extending another
   user type. This is what keeps the hierarchy exactly one level deep.
2. `name` must not collide with a canonical type (or, in `validate_user_type`,
   with an existing user type).
3. No redefining an inherited field name — additive only.
4. Field `type` must be one of `string | array | datetime | enum | boolean`.
5. Name must match `^[a-z][a-z0-9-]*$`.

An accepted user type gets `required_fields` / `optional_fields` **flattened at
load time** from parent + own. There is no runtime inheritance walk; `TypeDef`
carries the resolved field lists. Note the asymmetry: `subtype_fields` are *not*
inherited by user types — only canonical types get subtype-specific fields.

**Relations and schemes:** simpler — a user entry is rejected only on name
collision with a canonical one. `validate_user_relation` additionally *warns*
(does not reject) when `inverse_of` names an unknown relation or when the named
inverse points somewhere else, i.e. an asymmetric pair.

---

## 4. Loading, singletons, and the references fallback

All three registries use the identical module-level singleton pattern:

```python
_registry: Optional[XRegistry] = None
_registry_vault: Optional[Path] = None

def get_x_registry(vault_root=None) -> XRegistry: ...
def reset_x_registry() -> None: ...
```

Resolution order in `get_*`:

1. If `vault_root` is given, look for `<vault>/meta/<file>.yaml`.
2. If that path does not exist, **fall back to `src/loci/skills/references/`** and
   drop the user file entirely.
3. Cache. The cache is keyed on `vault_root`, so switching vaults reloads; the
   same vault reuses.

That fallback is why `tests/fixtures/vault/` has **no `meta/` directory**
and tests still get a full registry. Do not add a partial `meta/` dir to the
fixture vault — a partial dir defeats the fallback per-file and silently loads
an incomplete registry (see CLAUDE.md).

**In tests, always reset.** The singleton outlives a test function and will leak
a previous vault's ontology into the next test:

```python
@pytest.fixture(autouse=True)
def clean_registries():
    reset_registry(); reset_relation_registry(); reset_scheme_registry()
    yield
    reset_registry(); reset_relation_registry(); reset_scheme_registry()
```

`api.define_type` and `api.define_relation` call the matching `reset_*` after
appending to the user file, so the new definition is live for the very next
call. Any future writer of a registry file must do the same.

---

## 5. Where validation actually happens

Three enforcement points, with deliberately different strictness:

| Point | Module | Types | Relations | Schemes |
|---|---|---|---|---|
| `write_vault` | `tools/write_file.py::write_item` | **blocks** — unknown type raises; missing required field or bad enum returns `{"errors": [...]}` | **blocks** — returns `{"errors": [...]}` | *not yet* (TODO, Phase 5) |
| `patch_vault` | `tools/write_file.py::patch_item` | not re-validated | **warns** — `relation_warnings` in the result | *not yet* (TODO, Phase 5) |
| `lint_vault` | `tools/vault_linter.py::lint_file` | **error** on unknown type, missing required field, bad enum | **warning** on unknown relation type, dangling uid | **error** on missing/unknown scheme and missing scheme-required fields |

The philosophy: creation is strict, mutation is permissive, and the linter is
the safety net that finds drift after the fact (an ontology change can
retroactively invalidate nodes written months ago — the save skill surfaces this
at Step 0.5 as "ontology drift").

Subtype-aware enums matter at both write and lint: `TypeDef.enum_constraints()`
takes a `subtype` argument, and callers pass `frontmatter["subtype"]` so that
e.g. `genre` on `asset/book` is checked. If you add a subtype-scoped field, make
sure the caller is passing the subtype through.

---

## 6. Field layering on a node

A node's legal frontmatter is the union of three layers:

1. **Base fields** — `uid, type, title, author, state, created_at, updated_at,
   archived_at, tags, domains, summary, relations, references` (+ optional
   `language, aliases, has_asset`). Every node has these regardless of type.
2. **Type fields** — from the `types:` entry in `ontology.yaml` (or the
   flattened parent+own set for a user type).
3. **Subtype fields** — from `subtypes:` under a canonical type; only applied
   when the node's `subtype` matches. Currently only `asset/book` uses this, and
   it also carries a `body_template`.

⚠️ **Base fields are declared in `ontology.yaml` but nothing loads them.**
`TypeRegistry` only parses the `types:` key. The base list is duplicated as
`BASE_REQUIRED` in `vault_linter.py` and again as the literal frontmatter dict
in `write_file.py::write_item`, and `BASE_STATE_VALUES` is hardcoded in the
linter with a standing TODO. **Changing `base_fields:` in the YAML alone changes
nothing at runtime** — you must edit all three places. Same for `state`'s enum.

---

## 7. Recipes

### Add a canonical type

1. Add the entry to `ontology.yaml` under `types:` with `extends: null`,
   a `description`, and `fields.required` / `fields.optional`.
2. Add a one-line row to `type-dictionary.md` and a branch to the decision tree
   in `type-decision.md`.
3. Bump `META_VERSION` in `vault_init.py` so existing vaults get the new file.
4. Add a color to `TYPES` in `app/src/constants.js` — the UI list is hardcoded
   and a type missing from it renders without a dot color.
5. Check the save skill (`src/loci/skills/loci-save/SKILL.md`) for whether the new
   type needs classification guidance. There is nothing to bump: the MCP server
   serves the procedure live.
6. Tests: a write happy path, a missing-required-field rejection, a bad-enum
   rejection, and a lint case. Plus an e2e test if the UI renders it.

### Add a canonical relation

1. Add the entry to `relation-dictionary.yaml` with `name`, `group`,
   `description`, and `inverse_of` if it has one — **and add the inverse's
   `inverse_of` pointing back**, or `validate_user_relation` will report the
   pair as asymmetric later.
2. Mirror the human-readable note in `relation-dictionary.md`.
3. Bump `META_VERSION`.

### Add a canonical scheme

1. Add the entry to `scheme-dictionary.yaml` with `required_fields`,
   `optional_fields`, and `capabilities` (a subset of `resolve`, `enumerate`).
2. If it declares a capability, implement a resolver in `src/loci/tools/resolvers/`
   and add it to `_RESOLVER_FACTORIES` in `resolvers/dispatcher.py` (registration
   is static) — the registry only *declares* capabilities, it does not provide
   them. Most remote schemes route to `ExternalResolver`.
3. Bump `META_VERSION`.

### Add a whole new meta file

Follow the six-step checklist in CLAUDE.md ("Meta file sync"): create it here,
list it in `META_FILES` or `USER_META_FILES`, bump `META_VERSION`, add the key
to `read_meta`'s `file_map` in `api.py`, document it in the `read_meta` docstring
in `mcp_server.py`, and update whichever skill should read it. Skipping the
`file_map` step produces a file that exists in the vault and is unreachable —
see §8.

### Add a whole new registry

See the eight-step checklist in CLAUDE.md ("Adding a new registry"). Mirror
`relation_registry.py` — it is the smallest complete example of the pattern.

---

## 8. Known gaps and traps

Recorded so the next person doesn't rediscover them the hard way.

- **`base_fields` in `ontology.yaml` is decorative.** Nothing parses it. See §6.
- **`type-decision.md` is unreachable at runtime.** `loci-save/SKILL.md` tells
  the model to call `read_meta(file="type-decision")`, but that key is absent
  from `file_map` in `api.py`, and the file is absent from `META_FILES` so it
  is never seeded either. The call returns `Unknown meta file: 'type-decision'`.
  Fixing it means adding it to both lists and bumping `META_VERSION`.
- **The UI's type list is hardcoded.** `app/src/constants.js` `TYPES` does not
  come from the ontology. The `log` type is in `ontology.yaml` but not in
  `TYPES`. Any type added to one and not the other drifts.
- **`has_asset` is not validated on write or patch.** Both paths carry an
  explicit `TODO Phase 5` comment; only `lint_vault` checks scheme validity
  today. A node with an unknown scheme can be written and only surfaces at lint.
- **`patch_item` does not re-validate type fields.** You can patch a node into
  violating its own type's required fields; the linter is the only backstop.
- **`is_canonical` differs between registries.** `TypeRegistry.is_canonical`
  means `extends is None`; `RelationRegistry.is_canonical` means "came from the
  canonical file". They are not the same predicate.
- **`yaml.safe_load` eats datetime strings.** `patch_item` explicitly converts
  `datetime` objects back to `YYYY-MM-DDTHH:MM:SSZ` strings before dumping.
  Any new code that round-trips frontmatter must do the same or it will rewrite
  timestamp formats across the vault.
- **Reseeding is silent and automatic.** `check_meta_version()` runs on the
  first vault-touching tool call of a process — `requires_vault` → `ensure_ready()`,
  once per vault root — and overwrites every `META_FILES` entry when the vault
  is behind. `set_vault_root` does the same upgrade inline for the vault it
  adopts. Which version it compares against depends on the mode: a `config.yml` install
  reads `meta_version` from the config, while `LOCI_VAULT_ROOT` (Docker) reads
  `meta/.meta-version` inside the vault, since the image's `config.yml` does not
  survive a restart. Both modes write the in-vault marker, so a vault can move
  between them without being mistaken for stale.
- **An unversioned vault with a complete `meta/` is adopted, not reseeded.**
  The marker did not always exist, so its absence is not evidence of staleness.
  A vault holding every `META_FILES` entry is taken as current and the marker is
  backfilled. The cost: a genuinely old vault that is merely file-complete never
  gets upgraded.
- **Seeding is skipped when the vault directory is absent**, rather than
  creating it. Under Docker a missing directory means the volume was not
  mounted, and seeding into the container's own filesystem would report success
  for files discarded on the next run. `http_server.py` has no `requires_vault`
  guard and never calls `check_meta_version` at all, so an HTTP-only vault is
  never seeded — reads fall back to this directory, and `write_meta` creates
  `meta/` on demand. Every upgrade path (`ensure_env_vault`,
  `_check_meta_version`, `init(force=True)`) therefore calls
  `create_vault_structure` before `reseed_meta`: the vault may exist with no
  `meta/` in it at all, and `reseed_meta` writes into that directory rather
  than creating it.
- **A vault that is present but empty is left alone when the config already
  records a `meta_version`.** Everything that writes `vault_root` into the
  config also seeds `meta/`, so that combination means the content went away —
  a sync folder remounted as a placeholder. Seeding there would stamp both the
  config and the in-vault marker as current, and the reseed would never run
  once the real files came back.

---

## 9. The skill ↔ tool contract

The ontology is consumed by an LLM, not just by code, so a change here is only
half done until the skills agree. When you change any file in this directory,
walk the "Skill ↔ Tool sync rule" in CLAUDE.md in both directions. There is
no version to bump — the MCP server serves each procedure live — but keep the
frontmatter untouched unless the trigger description genuinely changed, since
that is the one part that reaches the installed stub.

Relevant tool surface:

| Tool | Purpose |
|---|---|
| `read_meta(file=...)` | read any meta file the map exposes |
| `write_meta(file=...)` | write — **only** `tag-dictionary`, `foreign-definitions`, `ontology-user` |
| `validate_type(...)` | dry-run a user type definition; writes nothing |
| `define_type(...)` | validate, append to `ontology-user.yaml`, reset the registry |
| `define_relation(...)` | same, for `relation-dictionary-user.yaml` |
| `lint_vault()` | full-vault validation against all three registries |

There is no `define_scheme` — user schemes must be hand-edited into
`scheme-dictionary-user.yaml`.

---

## 10. Tests

| Area | File |
|---|---|
| Type loading, user-type rules, `validate_user_type` | `tests/test_type_registry.py` |
| Relation loading and validation | `tests/test_relation_registry.py` |
| Scheme loading and validation | `tests/test_scheme_registry.py` |
| `define_type` end to end | `tests/test_define_type.py` |
| `define_relation` end to end | `tests/test_define_relation.py` |
| Write-time enforcement | `tests/test_write_file.py` |
| Lint rules | `tests/test_vault_linter.py`, `test_has_asset_lint.py` |
| Seeding and `META_VERSION` | `tests/test_vault_init.py` |

Run `make test-fast` while iterating on registry code; `make test` before
opening the PR.
