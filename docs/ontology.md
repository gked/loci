# The Ontology, From the Repo Side

The user's guide to the ontology — what types, relations, and schemes are, how to extend them, and when each rule is enforced — is [`ontology-guide.md`](../src/loci/skills/references/ontology-guide.md). It ships inside the package and is seeded into every vault at `meta/ontology-guide.md`, so it travels with your notes. This page is the shorter, repo-side view: what the registries hold and how they are versioned.

---

## Type System

Every vault node has a **type**. The right question when choosing one is not "what fields do I need?" but **"what question does this node answer?"**

| Type | The question it answers |
|---|---|
| `document` | What do I think or know about X? |
| `article` | What does this external source say? |
| `bookmark` | Where is this thing? |
| `conversation` | What did we discuss? |
| `project` | What am I working on? |
| `task` | What do I need to do? |
| `event` | What happened, and when? |
| `entity` | Who or what is this real-world actor? |
| `procedure` | How do I do X? |
| `topic` | What organizes this domain? |
| `asset` | What do I own? |
| `log` | What was my experience of engaging with X? |

**The common mistake:** thinking "this node has text, so it must be document-like." All vault nodes can have a text body. That is not what defines the type.

`document` is a **composition**: something that stands alone and matures over time (`status: draft → evergreen`). `log` is a **record**: it cannot exist without a subject (`subject_uid`), it doesn't mature, it completes. A reading log has text. So does a task description. Neither is a document.

### Type or tag?

The type list is short, and stays short because a candidate has to earn its place. Three questions, and a new type must answer **yes to at least one**:

1. Does it have fields no other type has?
2. Will you query for it exclusively, in ways you'd never query other types?
3. Does it behave differently in the system (display, ingestion, validation, relationships)?

If all three are no, it's a tag. This is why `recipe`, `workout`, and `playbook` are all `procedure` with a tag, and why `book` is `asset` with `subtype: book` rather than a type of its own.

Types can declare **subtypes** that add fields (e.g. `asset` / `subtype: book` adds `genre` and a body template). User-defined types extend a canonical parent and are registered in `ontology-user.yaml`; they inherit all parent fields and can add new ones, one level deep.

### Relations

Edges are typed, directional, and drawn from a closed vocabulary of 27 relations in six groups:

| Group | Relations |
|---|---|
| `dependency-sequencing` | `depends-on`, `enables` |
| `structural-ownership` | `belongs-to`, `parent-of`, `is-part-of`, `has-part` |
| `provenance-derivation` | `is-based-on`, `same-work-as`, `supersedes`, `version-of`, `implements` |
| `semantic` | `about`, `mentions`, `influences`, `supports`, `contradicts`, `inspired-by`, `informs`, `informed-by`, `references`, `involves`, `instance-of`, `used-in`, `uses` |
| `entity` | `works-at`, `follows` |
| `generic` | `relates-to` (weak-association fallback) |

Inverses are collapsed: store one directed edge and derive the reverse rather than writing both. For `depends-on` / `enables`, the edge lives on the dependent node. Anything outside this vocabulary is rejected on write; add your own to `relation-dictionary-user.yaml` via `define_relation` first.

For the full walkthrough — types, relations, schemes, how to extend them, and when each rule is enforced — see [the ontology guide](../src/loci/skills/references/ontology-guide.md). A copy is seeded into every vault at `meta/ontology-guide.md`, so it travels with your notes.

---

## Schema Versioning

Meta files are seeded into `vault/meta/` from `src/loci/skills/references/`, which is the source of truth for what a fresh vault gets. `vault_init.py` holds the current `META_VERSION` and two lists:

- `META_FILES`: reseeded on every `META_VERSION` bump
- `USER_META_FILES`: seeded once and never overwritten — the `-user.yaml` extension
  files, plus `tag-dictionary.md` and `foreign-definitions.md`, which the model
  writes to at runtime

The config file tracks the `meta_version` the vault was last seeded at. On startup, a vault behind `META_VERSION` is reseeded and its config updated.

### Adding a new type, relation, scheme, or field (non-breaking)

1. Edit the relevant file in `src/loci/skills/references/`
2. Increment `schema_version` in that file and `META_VERSION` in `vault_init.py`
3. Add the `read_meta` key in `api.py` and update the `server.py` docstring if it's a new file
4. Update any skill that should read or validate against it

### Breaking changes (rename, remove, restructure)

Breaking changes require an explicit migration script that reads the live vault, transforms affected nodes, and updates `meta_version` in `config.yml`. Document the change in a changelog entry.

### Why two copies?

The vault meta files are user-owned, accumulating customizations (new tags, local schema tweaks) that the project seeds don't have. The `src/loci/skills/references/` files are the template. Non-breaking additions are auto-reseeded; breaking changes always require explicit migration.
