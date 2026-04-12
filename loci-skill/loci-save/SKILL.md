---
name: loci-save
skill_version: 4
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

## Version Check (run before anything else)

This skill is at `skill_version: 4`.

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

---

### Step 1 — Classify the content

Call `loci__read_meta(file="type-dictionary")` to get the type vocabulary.
Call `loci__read_meta(file="type-decision")` to get the classification guide. Follow it to determine the type and format tags.

If `bookmark` is chosen, call `loci__fetch_url_metadata(url)` immediately to retrieve
title, site name, and description. Use these to populate the title, site_name, and summary
fields — do not ask the user for them unless the fetch fails.

---

### Step 2 — Generate frontmatter

Call `loci__generate_uid` to get the UID.

Call `loci__read_meta(file="tag-dictionary")` and prefer existing tags over
synonyms. If a new tag is likely to recur, add it via `loci__write_meta`
before writing the item.

Call `loci__read_meta(file="field-dictionary")` to get the current field
definitions for all types. Use this as the authoritative source for which
fields to include, their types, valid enum values, and whether they are required.

Call `loci__read_meta(file="relation-dictionary")` to get the current relation
type vocabulary. Use this when choosing the `type` field for any relation — pick
the most specific type that fits rather than defaulting to `relates-to`.

**Relations format:**
```yaml
relations:
  - uid: b7d4e1a2
    type: influences
```

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

## Edge Cases

**Deleting an item:** call `loci__list_vault` to identify the file, read it back to confirm
it's the right one, then ask the user explicitly before calling `loci__delete_vault`.
Deletion is permanent — there is no undo.

**No clear title:** generate from first sentence or ask. Never leave blank.

**Very long content:** summarize in `summary`, keep full content in body.
