---
name: locus-save
description: >
  Save any piece of content — a note, article, conversation, task, project,
  event, entity, procedure, topic, or reference — into the Locus personal
  knowledge vault. Use this skill whenever the user says "save this", "add
  this to my vault", "capture this", "remember this", "log this", "store
  this", or any similar phrasing. Also use when the user shares a URL, a
  piece of text, or a conversation excerpt and implies they want it persisted.
  Triggers for both new content and updates to existing vault items.
---

# Locus Save Skill

Saves content to the Locus vault as a structured Markdown file with YAML
frontmatter. Works in both Claude.ai (via write abstraction layer) and
Claude Code (direct filesystem write to Nextcloud sync folder).

---

## File Locations

Two distinct file locations are used by this skill. Do not confuse them.

**Skill bundle** (read-only, ships with the skill):
```
locus-save-skill/
  SKILL.md
  references/
    type-fields.md       <- type-specific frontmatter fields (Claude's instructions)
```

**Locus vault** (read/write, lives in Nextcloud):
```
<vault_root>/
  /notes/
  /articles/
  /conversations/
  /projects/
  /tasks/
  /events/
  /entities/
  /procedures/
  /topics/
  /references/
  /meta/
    config.yml           <- vault configuration including vault_root path
    type-dictionary.md   <- canonical type vocabulary (runtime lookup)
    tag-dictionary.md    <- freeform tag vocabulary (runtime lookup)
    foreign-definitions.md <- external source schemas (grows over time)
```

`<vault_root>` is resolved at runtime from `config.yml` (see Step 0).

---

## Save Workflow

Follow these steps in order for every save operation.

### Step 0 — Resolve vault configuration

Before doing anything else, check for config and tools. Follow this decision tree exactly.

---

**Check 1: Is config present?**

```
Look for: ~/.locus/config.yml
```

If found → load it, extract `vault_root`, proceed to Check 2.
If not found → this is a first run. Go to **First-Run Setup** below.

---

**Check 2: Does vault_root exist and have the expected structure?**

```
Check that <vault_root>/meta/type-dictionary.md exists.
```

If yes → configuration is valid. Proceed to Step 1.
If no → vault structure is incomplete. Run:
```bash
python tools/vault_init.py
```
Then proceed to Step 1.

---

**First-Run Setup (no config found)**

Tell the user:
```
Locus is not set up yet. I'll walk you through it now.
This will take about a minute.
```

Then execute the following steps in order, pausing for user input where indicated:

**A. Verify repo is cloned**
```bash
ls tools/vault_init.py
```
If file not found:
```
I can't find the Locus tools. Please clone the repo first:

  git clone https://github.com/gked/locus.git
  cd locus

Then try again.
```
Stop. Do not proceed.

**B. Install dependencies**
```bash
pip install -r requirements.txt
```
Tell the user: "Installing dependencies..."

**C. Ask for Nextcloud path**
Ask the user:
```
Where is your Nextcloud folder on this machine?
(e.g. ~/Nextcloud or /Users/yourname/Nextcloud)
```
Wait for response. Use their answer as `nextcloud_root`.

**D. Ask for vault folder name**
Ask the user:
```
What should the vault folder be called inside Nextcloud?
Press Enter to use the default: locus
```
Wait for response. Default to `locus` if empty.

**E. Write config and initialize vault**
```bash
python tools/vault_init.py
```
The script will prompt for the same values — pass the answers from C and D.

Alternatively, write config directly:
```bash
mkdir -p ~/.locus
cat > ~/.locus/config.yml << EOF
vault_root: <nextcloud_root>/<vault_name>
webdav_url: null
created_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
version: 1
EOF
python tools/vault_init.py
```

**F. Confirm setup complete**
```
Locus is ready.
Vault created at: <vault_root>

You can now save content. Try:
  "Save this as a note: Locus is set up and working."
```

---

### Step 1 — Classify the content

Determine the type. First try to read `<vault_root>/meta/type-dictionary.md`
for any custom types the user has added. Fall back to the canonical vocabulary
below if the file does not exist.

```
note         — freeform thought or observation
article      — external content consumed (URL required)
conversation — saved LLM or human conversation
project      — ongoing work with goals and milestones
task         — discrete actionable item with due date and status
event        — point-in-time or period occurrence
entity       — real-world actor: person, company, org, institution
procedure    — repeatable process with ordered steps and expected outcome
topic        — organizing hub for a subject area
reference    — pointer to external content (hybrid ownership model)
```

If unsure between two types, ask the user. Do not guess — type affects
folder placement and frontmatter fields.

**Subtype tags to apply automatically:**
- `article` -> add format tag: #book, #paper, #video, or #article
- `entity` -> add subtype tag: #person, #company, #organization, #institution
- `procedure` -> add domain tag: #recipe, #workout, #protocol, #playbook, #tutorial

---

### Step 2 — Generate frontmatter

Generate a complete YAML frontmatter block using the base schema below.
For type-specific fields, read from the skill bundle at:
`locus-save-skill/references/type-fields.md`

**Base schema (all types):**
```yaml
---
uid: <8-char hex, e.g. a3f9c2b1>        # generated by code: uuid.uuid4().hex[:8]
                                         # Claude Code: execute Python snippet
                                         # Claude.ai: delegated to MCP layer (TBD)
type: <type>
title: <concise, descriptive title>
author: self                             # "self" for user-produced content; entity UID or name for external
created_at: <ISO 8601, e.g. 2026-03-21T14:32:00Z>
updated_at: <same as created_at on first save>
archived_at: null
tags: []                                 # 3-6 freeform lowercase hyphenated tags
                                         # consult <vault_root>/meta/tag-dictionary.md first
                                         # prefer existing tags over synonyms
                                         # add new tags to tag-dictionary.md if they'll recur
domains: []                              # one or more from fixed taxonomy below
summary: <one paragraph — what this is, why it matters, key insight>
relations: []                            # links to other vault nodes by UID
references: []                           # pointers to external content
---
```

**Domain taxonomy (fixed — pick one or more):**
```
technology-engineering
science-research
business-strategy
finance-economics
health-biology
philosophy-ethics
creativity-design
personal-development
current-events-society
```

**Relations format:**
```yaml
relations:
  - uid: b7d4e1a2
    type: influences
  - uid: c9f2d3b4
    type: belongs-to
```

**References format (for hybrid ownership — external content):**
```yaml
references:
  - url: https://example.com
    title: The Article Title
    source_type: article
```

---

### Step 3 — Generate filename and path

```
filename: YYYY-MM-DD-slugified-title.md
  - date: today's date
  - slug: lowercase, hyphens, strip special chars, max 60 chars
  - example: 2026-03-21-why-i-left-twitter.md

full path: <vault_root>/<type-folder>/<filename>
  - example: ~/Nextcloud/locus/notes/2026-03-21-why-i-left-twitter.md
```

---

### Step 4 — Scan for links and tag matches

Before writing, scan both the content and the user's framing (how they described
the item) for signals that it belongs to a project, topic, or entity, and for
tags that should be added. Handle each category below.

---

#### 4a — Projects

Scan for named projects in the content or user's framing (e.g. "this is for the
locus project", "part of X initiative").

1. Check if a matching project node exists in `<vault_root>/projects/`
2. Present suggestion:
   ```
   This looks related to the [Project X] project.
   Link it? [yes / no / create project node for X]
   ```
3. On confirmation, add the project UID to `relations` with type `belongs-to`
4. On "create project node", trigger a new save for that project first, then link back

---

#### 4b — Topics

Scan for subject areas or themes that could map to a topic node.

1. Check if a matching topic node exists in `<vault_root>/topics/`
2. Present suggestion:
   ```
   This looks related to the topic [X].
   Link it? [yes / no / create topic node for X]
   ```
3. On confirmation, add the topic UID to `relations` with type `belongs-to`
4. On "create topic node", trigger a new save for that topic first, then link back

---

#### 4c — Entities

Scan for mentions of specific people, companies, organizations, or institutions.

1. Check if an entity node already exists in `<vault_root>/entities/`
2. Present suggestion:
   ```
   I noticed mentions of [Person X] and [Company Y].
   Should I link this item to their entity nodes?
   [yes / no / create new entity for X]
   ```
3. On confirmation, add the entity UID to the `relations` field
4. On "create new entity", trigger a new save for that entity first, then link back

---

#### 4d — Tags

After determining tags in Step 2, check each proposed tag against
`<vault_root>/meta/tag-dictionary.md`. If a proposed tag is not in the
dictionary and seems likely to recur, add it to the dictionary before writing
the file. If a proposed tag is a synonym of an existing tag, prefer the
existing one.

---

**Do not auto-link without confirmation.** Suggestions only — user confirms.
Present all suggestions together in one prompt, not one at a time.

---

### Step 5 — Write the file

**Claude Code (direct filesystem):**
```python
path = f"{vault_root}/{type_folder}/{filename}"
# write frontmatter + content body to path
```

**Claude.ai (abstraction layer):**
```
write_to_vault(path, content)
# MCP implementation TBD — placeholder until WebDAV MCP is built
```

After writing, confirm to the user:
```
Saved: <vault_root>/notes/2026-03-21-why-i-left-twitter.md
UID: a3f9c2b1
Type: note
Links: none
```

---

### Step 6 — Foreign content schema discovery (external sources only)

If the content comes from an external app (Jira, calendar, email, Slack, etc.)
and no schema exists yet for that source type:

1. Read `<vault_root>/meta/foreign-definitions.md`
2. If no schema found for this source type, enter discovery:
   ```
   This looks like content from [source]. I don't have a schema for this yet.
   What metadata matters to you from this source?
   Available fields: [list fields visible in content]
   ```
3. Keep prompting until the user confirms the schema
4. Append the confirmed schema to `<vault_root>/meta/foreign-definitions.md`
5. Use that schema for all future saves from the same source type

---

## Edge Cases

**Content with no clear title:** generate a title from the first sentence or
ask the user. Never leave title blank.

**Duplicate detection:** before writing, check `<vault_root>/<type-folder>/`
for files with similar titles or the same URL. If a likely duplicate is found:
```
A similar item already exists: [title] (uid: xxxxxxxx)
Save as new item, or update the existing one?
```

**Very long content:** summarize in the `summary` field. Store full content
in the body. Do not truncate the body.

**Unknown type:** ask the user rather than defaulting to `note`. Type affects
folder placement and fields.

---

## Reference Files

**Skill bundle (read-only, always available):**
- `locus-save-skill/references/type-fields.md` — type-specific frontmatter fields

**Vault meta (read/write at runtime):**
- `<vault_root>/meta/config.yml` — vault path and connection config
- `<vault_root>/meta/type-dictionary.md` — canonical type vocabulary
- `<vault_root>/meta/tag-dictionary.md` — freeform tag vocabulary
- `<vault_root>/meta/foreign-definitions.md` — external source schemas
