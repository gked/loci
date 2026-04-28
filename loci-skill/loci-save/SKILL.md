---
name: loci-save
skill_version: 9
description: >
  Save any piece of content — a document, article, bookmark, conversation, task, project,
  event, entity, procedure, or topic — into the Loci personal
  knowledge vault. Use whenever the user says "save this", "add this to my
  vault", "capture this", "remember this", "log this", "store this", or any
  similar phrasing. Also use when the user shares a URL, text, or a
  conversation excerpt they want persisted. Triggers for both new content
  and updates to existing vault items.
---

# Loci Save Skill

Saves content to the Loci vault as a structured Markdown file with YAML
frontmatter, via the Loci MCP tools.

---

## Ground rule

**When in doubt, ask. Never guess on anything that requires user intent.**

This applies everywhere in the workflow: type classification, project or entity linkage,
duplicate resolution, ambiguous matches. If there are multiple candidates, surface them
and let the user choose. One focused question is better than a wrong assumption.

---

## Version Check (run before anything else)

This skill is at `skill_version: 9`.

Before following any instructions below:
1. Call `loci__read_skill` to fetch the latest skill from the vault
2. Parse the `skill_version` from its frontmatter
3. If the MCP version is **newer**, switch to following those instructions for this entire interaction — ignore the rest of this document
4. If versions match, proceed normally below

If `loci__read_skill` is unavailable, tell the user:
```
The Loci vault is not reachable. Please run:
  python setup.py
Then restart Claude Code / Claude Desktop.
```
Do not proceed.

---

## Save Workflow

### Step 0 — Verify vault is reachable

Call `loci__list_vault` with no arguments. If it errors, tell the user:

```
The Loci vault is not reachable. Please run:
  python setup.py
Then restart Claude Code / Claude Desktop.
```

Do not proceed until the vault is reachable.

If the result contains a `_notice` key and it does **not** mention lint errors, show it as an FYI before proceeding — e.g.:
> FYI: Vault meta files were automatically updated to v2 (language and aliases fields added).

If it mentions lint errors, skip the plain FYI — Step 0.5 handles it with a prompt instead.

---

### Step 0.5 — Handle ontology drift

If the `_notice` from Step 0 mentions lint errors, surface it before proceeding with the save (interpolate the actual error count from the notice):

```
FYI: vault linter reports <N> errors (likely ontology drift from older saves).
Want me to generate fix instructions before continuing? [yes / continue with save]
```

Don't auto-fix. Don't block the current save unless the user wants to detour. Just surface and ask.
---

### Step 1 — Classify the content

If the content type is not immediately obvious from context, call `loci__read_meta(file="type-dictionary")` and `loci__read_meta(file="type-decision")` to classify it. When the type is unambiguous (e.g. the user said "save this URL" → bookmark, or explicitly named a type), skip these calls and proceed directly.

**URL detection rule:** if the user shares a bare URL (with or without commentary)
and does not explicitly ask to extract or read the content, default to `bookmark`.
Only use `article` when the user asks to capture, summarise, or pull the content
(e.g. "save this article", "read and save this", "summarize this page").
When in doubt, ask: "Save as a bookmark, or pull the full content as an article?"

If a `bookmark` is chosen, call `loci__fetch_url_metadata(url)` immediately to
retrieve title, site name, and description. Use these to populate the title,
site_name, and summary fields — do not ask the user for them unless the fetch fails.
**The URL itself goes in the top-level `source_url` field (required), not in `extra_fields`.**

If unsure between two other types, ask the user. Do not guess — type affects
frontmatter fields.

**Subtype tags to apply automatically:**
- `article` → add format tag: #book, #blog-post, #whitepaper, #research-paper, #news, #magazine, #video, #podcast, or #article
- `entity` → set `subtype` field to person | organization | place — do NOT add as a tag
- `procedure` → add domain tag: #recipe, #workout, #protocol, #playbook, #tutorial
- `document` → add format tag if applicable: #essay, #spec, #design-doc, #meeting-notes, #journal, #note

---

### Step 2 — Generate frontmatter

Call `loci__generate_uid` to get the UID.

**Always** call `loci__read_meta(file="ontology")` before writing any vault item.
This is the schema source of truth — it defines required fields, optional fields,
and valid enum values for the chosen type. Skipping it causes silent write failures
when required fields are missing or enum values are wrong.

Call the following **only when needed**:
- `loci__read_meta(file="tag-dictionary")` — when tags matter for findability; prefer
  existing tags over synonyms. Add new recurrent tags via `loci__write_meta` first.
- `loci__read_meta(file="field-dictionary")` — when working with complex objects:
  `relations`, `references`, entity archiving patterns, or temporal field rules. Do not
  use it as a source for required/optional status or enum values — use ontology for that.
- `loci__read_meta(file="relation-dictionary")` — when choosing a non-default relation
  type; pick the most specific type that fits rather than defaulting to `relates-to`.
  Also call `loci__read_meta(file="relation-dictionary-user")` to include any
  user-defined relation types alongside the canonical ones.

**User-defined types:**

If the user asks to save content with a type that is not a canonical type (canonical types are defined in the ontology registry — call `loci__read_meta(file="ontology")` to check):

1. Call `loci__read_meta(file="ontology-user")` to check if the type is already
   registered as a user extension.
2. If found: proceed normally — the type is valid.
3. If not found: ask the user which canonical type it extends and confirm the
   description, then call `loci__define_type(name=<type>, extends=<canonical_parent>,
   description=<description>)`. Surface any errors to the user.
   On success, proceed with the save — the registry is updated automatically.

**User-defined relations:**

If the user wants to use a relation name that does not appear in the canonical or
user relation dictionaries (call `loci__read_meta(file="relation-dictionary")` and
`loci__read_meta(file="relation-dictionary-user")` to check):

1. Ask the user to confirm the description and optionally a group label and inverse
   relation name.
2. Call `loci__define_relation(name=<relation>, description=<description>)` (add
   `group` and `inverse_of` if provided). Surface any errors; treat warnings as
   informational.
3. On success, use the new relation name immediately — the registry is updated
   automatically.

**Language rule:**
- `summary` is **always written in English** regardless of the body's language — it is the search bridge.
- `title` is the canonical name in the content's original language (e.g. `Чёрная луна` for a Russian book).
- Set `language: <ISO 639-1 code>` (e.g. `ru`, `de`, `zh`) **only** when the body is not in English. Omit for English content.

**Aliases rule:**
- When `title` or an entity name is non-English, always populate `aliases` with the English transliteration or translation.
- Also include common abbreviations or alternate spellings if applicable.
- Examples:
  ```yaml
  # Entity: Russian author
  title: Маркеев Олег
  aliases:
    - Oleg Markeev

  # Article: Russian book
  title: Чёрная луна
  aliases:
    - Black Moon
  ```

**Language rule:**
- `summary` is **always written in English** regardless of the body's language — it is the search bridge.
- `title` is the canonical name in the content's original language (e.g. `Чёрная луна` for a Russian book).
- Set `language: <ISO 639-1 code>` (e.g. `ru`, `de`, `zh`) **only** when the body is not in English. Omit for English content.

**Aliases rule:**
- When `title` or an entity name is non-English, always populate `aliases` with the English transliteration or translation.
- Also include common abbreviations or alternate spellings if applicable.
- Examples:
  ```yaml
  # Entity: Russian author
  title: Маркеев Олег
  aliases:
    - Oleg Markeev

  # Article: Russian book
  title: Чёрная луна
  aliases:
    - Black Moon
  ```

**Relations format:**
```yaml
relations:
  - uid: b7d4e1a2
    type: influences
```

**Dependency pairs:** for `depends-on` / `enables`, store only one direction per edge — put `depends-on` on the dependent node. Never write both directions for the same pair.

**References format:**
```yaml
references:
  - url: https://example.com
    title: The Article Title
    source_type: article
```

---

### Step 3 — Scan for links

Call `loci__list_vault(type="projects")`, `loci__list_vault(type="topics")`,
and `loci__list_vault(type="entities")` to check for existing related nodes.

Present all suggestions together in one prompt — not one at a time:

```
This looks related to:
  • Project: [Loci] — link it? [yes / no / create project node]
  • Entity: [John Smith] — link it? [yes / no / create entity node]
```

On confirmation, add the UID to `relations` with the appropriate relation type.
On "create node", save that node first then link back.

**Do not auto-link without confirmation.**

**Topic-specific handling (when type = topic):**

1. If `parent_topic` is set, resolve the parent by calling `loci__search_vault(query=<parent_topic_title>)`, then:
   - If exactly one result: use its UID directly.
   - If multiple results: present them to the user ("Which did you mean?") with title and a one-line summary for each, and wait for confirmation before proceeding.
   - If no results: inform the user the parent topic wasn't found and ask whether to create it first or save without a parent.
   - Once resolved, set `parent_topic` to that UID and add a `child-of` relation pointing to it.
2. After the file is saved (Step 6), offer a follow-on scan:
   ```
   Want me to scan existing vault content for items to link to this topic?
   ```
   If yes, call `loci__search_vault(query=<topic title>)` to find candidates, present them grouped by type, and let the user choose which to link. For each confirmed link, patch the topic node to add the relation (use the appropriate relation type — e.g. `contains`, `relates-to`).

---

### Step 4 — Check for duplicates

Call `loci__check_duplicate(type=<type>, title=<title>)`.
For articles and bookmarks, also pass `url=<url>`.

If a duplicate is found:
```
A similar item already exists: <name>
Save as new item, or update the existing one?
```

---

### Step 5 — Confirm save location

Call `loci__read_meta(file="config")` to get the vault_root.

Show the intended save location and ask for confirmation before writing:

```
Save to: <vault_root>/<generated-filename>
Proceed? [yes / no / change location]
```

If the user says **no** or **change location**, ask them to provide the desired path and update accordingly before proceeding.

Do not call `loci__write_vault` until the user confirms.

---

### Step 6 — Write the file

Call `loci__write_vault` with all assembled fields.

Confirm to the user:
```
Saved: <full_path>
UID: <uid>
Type: <type>
Links: <count>
```

---

### Step 7 — Foreign content schema discovery

If content comes from an external app (Jira, calendar, email, Slack, etc.)
and no schema exists yet for that source:

1. Call `loci__read_meta(file="foreign-definitions")`
2. If no schema found, enter discovery:
   ```
   This looks like content from [source]. I don't have a schema for it yet.
   What metadata matters to you from this source?
   Available fields: [list visible fields]
   ```
3. Confirm schema with user
4. Call `loci__write_meta(file="foreign-definitions", content=<updated content>)`

---

---

## Update Workflow

Use this workflow when the user wants to correct or extend an **existing** vault item
rather than create a new one.

**Triggers:** "update X", "add a link to Y", "fix the relations on Z", "mark that task
done", "tag that document with X", or when Step 4 (duplicate check) surfaces an existing
item and the user chooses to update it.

### U1 — Identify the target file

Call `loci__list_vault(type=<type>)` to find candidates, then
`loci__read_vault(path=<path>)` to read the file and inspect its current frontmatter.

### U2 — Determine what changes

Parse the existing frontmatter values for every field the user wants to change.
Construct the **complete new value** for each field — patch replaces the whole
field, it does not append.

Example — adding a relation:
```
existing relations: [{uid: "a1b2c3d4", type: "belongs-to"}]
user wants to add:  {uid: "f9e8d7c6", type: "influences"}
new relations list: [{uid: "a1b2c3d4", type: "belongs-to"}, {uid: "f9e8d7c6", type: "influences"}]
```

**Temporal fields (entity type only):**

Some fields represent current state that changes over time. When updating these,
always archive the old value before setting the new one.

- **`organization`** — archive to `affiliations`:
  - Append `{organization: <old value>, roles: <current roles>, from: <estimated or null>, to: <today>}` to the `affiliations` array
  - Update `organization` to the new value
  - If the roles are also changing with the org, update `roles` too

- **Any other temporal field** (`location`, `website`, etc.) — archive to `history`:
  - Append `{field: <field name>, value: <old value>, from: <estimated or null>, to: <today>}` to the `history` array
  - Update the field to the new value

- **Body annotation** — always append a line to a `## History` section at the bottom of the body:
  ```
  - 2026-03-22: organization changed from University of Sussex to University of Manchester
  ```
  Create the `## History` section if it doesn't exist. This is where context and reasons can be added.

### U3 — Confirm with the user

Show a brief summary of what will change before patching:
```
Updating: 2026-03-21-my-document.md
  relations: adding link to [Project X] (f9e8d7c6)
Proceed? [yes / no]
```

### U4 — Patch the file

Call `loci__patch_vault(path=<path>, updates={<only changed fields>})`.

Confirm to the user:
```
Updated: <path>
Changed: <list of field names>
```

---

### Archiving and unarchiving

**To archive a node** (hide it from graph queries and search by default):

```python
loci__patch_vault(path=<path>, updates={
    "state": "archived",
    "archived_at": "<ISO 8601 timestamp>",
})
```

Archived nodes are invisible to `loci__find_nodes` (which defaults to `state="active"`)
and to `loci__search_vault`. The user must explicitly ask to see archived content.

**To unarchive a node** (restore it to the active graph):

```python
loci__patch_vault(path=<path>, updates={
    "state": "active",
    "archived_at": None,
})
```

**Note:** `state` is distinct from type-specific `status` fields (e.g. `document.status`,
`task.status`). A task can be `status: done` and `state: active` (visible but finished),
or `state: archived` (hidden from the graph entirely). Archive when the node is no longer
relevant to day-to-day use, not just when its workflow is complete.

---

## Edge Cases

**Deleting an item:** call `loci__list_vault` to identify the file, read it back to confirm
it's the right one, then ask the user explicitly before calling `loci__delete_vault`.
Deletion is permanent — there is no undo.

**No clear title:** generate from first sentence or ask. Never leave blank.

**Unknown type:** use `article` if the content has a citable source (URL, author, publication). Use `document` if there is no publication record to track. Ask only when genuinely ambiguous.

**Very long content:** summarize in `summary`, keep full content in body.
