---
name: loci-save
description: >
  Save any piece of content — a note, article, conversation, task, project,
  event, entity, procedure, topic, or reference — into the Loci personal
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

Call `loci__read_meta(file="type-dictionary")` for any custom types the user
has added. Fall back to the canonical vocabulary:

```
note         — freeform thought or observation
article      — external content consumed and captured in full (URL required)
bookmark     — saved URL with light metadata only; default when user shares a URL
conversation — saved LLM or human conversation
project      — ongoing work with goals and milestones
task         — discrete actionable item with due date and status
event        — point-in-time or period occurrence
entity       — real-world actor: person, company, org, institution
procedure    — repeatable process with ordered steps and expected outcome
topic        — organizing hub for a subject area
reference    — pointer to external content (hybrid ownership model)
```

**URL detection rule:** if the user shares a bare URL (with or without commentary)
and does not explicitly ask to extract or read the content, default to `bookmark`.
Only use `article` when the user asks to capture, summarise, or pull the content.
When in doubt, ask: "Save as a bookmark, or pull the full content as an article?"

If a `bookmark` is chosen, call `loci__fetch_url_metadata(url)` immediately to
retrieve title, site name, and description. Use these to populate the title and
summary fields — do not ask the user for them unless the fetch fails.

If unsure between two other types, ask the user. Do not guess — type affects
folder placement and frontmatter fields.

**Subtype tags to apply automatically:**
- `article` → add format tag: #book, #paper, #video, or #article
- `entity` → add subtype tag: #person, #company, #organization, #institution
- `procedure` → add domain tag: #recipe, #workout, #protocol, #playbook, #tutorial

---

### Step 2 — Generate frontmatter

Call `loci__generate_uid` to get the UID.

Call `loci__read_meta(file="tag-dictionary")` and prefer existing tags over
synonyms. If a new tag is likely to recur, add it via `loci__write_meta`
before writing the item.

**Base schema (all types):**
```yaml
uid: <from loci__generate_uid>
type: <type>
title: <concise, descriptive title>
author: self                            # "self" for user content; entity name/UID for external
created_at: <ISO 8601, e.g. 2026-03-21T14:32:00Z>
updated_at: <same as created_at on first save>
archived_at: null
tags: []                                # 3-6 freeform lowercase hyphenated tags
domains: []                             # one or more from fixed taxonomy below
summary: <one paragraph — what this is, why it matters, key insight>
relations: []
references: []
```

**Domain taxonomy (fixed — pick one or more):**
```
technology-engineering, science-research, business-strategy,
finance-economics, health-biology, philosophy-ethics, creativity-design,
personal-development, current-events-society
```

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

**Type-specific fields** — merge into `extra_fields` when calling `loci__write_vault`:

- **bookmark:** `source_url` (required), `site_name` (from fetch)
- **note:** `status: draft | evergreen | archived`
- **article:** `source_url`, `author`, `published_at`, `format: article|book|paper|video`, `highlights: []`
- **conversation:** `participants: []`, `model`, `turns`, `platform: claude|chatgpt|human|other`
- **project:** `status: active|paused|completed|abandoned`, `goals: []`, `milestones: []`, `due_date`
- **task:** `status: todo|in-progress|done|cancelled`, `due_date`, `priority: high|medium|low`, `assignee`
- **event:** `start_at`, `end_at`, `location`, `participants: []`
- **entity:** `subtype: person|company|organization|institution`, `website`, `role`, `organization`, `industry`, `founded_at`
- **procedure:** `subtype: recipe|workout|protocol|playbook|tutorial`, `steps: []`, `expected_outcome`, `inputs: []`, `duration_minutes`
- **topic:** `status: active|archived`, `parent_topic`
- **reference:** `source_url`, `source_type`, `external_id`, `metadata: {}`

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
For articles, also pass `url=<url>`.

If a duplicate is found:
```
A similar item already exists: <name>
Save as new item, or update the existing one?
```

---

### Step 5 — Write the file

Call `loci__write_vault` with all assembled fields.

Confirm to the user:
```
Saved: <path>
UID: <uid>
Type: <type>
Links: <count>
```

---

### Step 6 — Foreign content schema discovery

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
done", "tag that note with X", or when Step 4 (duplicate check) surfaces an existing
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

### U3 — Confirm with the user

Show a brief summary of what will change before patching:
```
Updating: notes/2026-03-21-my-note.md
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

**Unknown type:** ask rather than defaulting to `note`.

**Very long content:** summarize in `summary`, keep full content in body.
