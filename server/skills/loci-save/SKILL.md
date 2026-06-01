---
name: loci-save
skill_version: 18
description: >
  Save any piece of content — a document, article, bookmark, conversation, task, project,
  event, entity, procedure, topic, asset, or log — into the Loci personal
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

This skill is at `skill_version: 18`.

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

**Binary file / media pattern (video, audio, image, PDF, ebook):**

Use `loci__save_asset` instead of `loci__write_vault` whenever the content is a
binary file. It writes the asset to `loci/assets/` and creates the vault proxy
node in one crash-safe sequence.

**Three scenarios — choose the right path:**

**1. File on disk (user provides a path)**
Call `loci__save_asset(source_path=<absolute_path>, ...)`. The server reads the
bytes directly — no file data passes through MCP, no size limit. This is always
the most reliable path.

**2. File dropped into the conversation (small/medium)**
Use when the file content landed in context (image, small PDF, generated text).
Call `loci__save_asset(content=<content>, is_base64=<True|False>, ...)`.
Treat formats as small enough for this path: images (jpg, png, gif, webp, svg),
PDFs and documents up to a few hundred KB, any text Claude generated.

**3. File dropped into the conversation (too large)**
Use when the file is a format that is inherently large, or when the content
appears truncated or unavailable in context. This includes: video (mp4, mov, avi,
mkv), audio (mp3, wav, flac, aac, m4a), raw images, and anything the user says
is large. Do **not** attempt inline — tell the user:

> This file is too large to save directly from the conversation. Please drop it
> into your `loci-stage/` folder, then ask me to run the inbox scan and I'll
> process it from there.

Once the user confirms the file is in `loci-stage/`, run:
`loci__scan_inbox` → `loci__approve_inbox_plan` → `loci__execute_inbox_file_batch`

The inbox workflow reads the file from disk — no size limit, nothing through MCP.

**Never** base64-encode a file yourself to pass it inline. If the file exists on
disk or belongs in loci-stage, always use `source_path` or the inbox workflow.

Set `node_type="asset"` and the appropriate `subtype` (e.g. `film`, `album`,
`book`, `image`). `save_asset` returns `{uid, asset_path, vault_path}` — confirm
all three to the user.

**Book & Library pattern:**
- **Saving an ebook or book you own** → `asset`, `subtype: book`. Always add `#book` tag for findability. Call `loci__read_meta(file="field-dictionary")` to get the body template, summary convention, and canonical genre list before writing.
- **Book genre** — set `genre` to exactly one canonical slug from the genre taxonomy in field-dictionary (e.g. `business-economics`, `body-mind-spirit`, `technology-computing`). This field is required for book nodes — do not leave it blank. If the genre is ambiguous, pick the closest match and note it in the body.
- **Book body** — use the `body_template` from field-dictionary: sections `## Bibliographic`, `## About`, `## Notes`. Fill in known values; leave blank lines blank.
- **Book summary** — overrides the English-only rule: for non-English books (e.g. `language: ru`), write summary in **both** languages — English paragraph first, native-language paragraph second. English-only books follow the standard rule.
- **Recording a reading** → `log` (canonical type). Required: `subject_uid` (the book asset's UID), `log_status` (in-progress | finished | abandoned). Add tag `reading`. Also add an `about` relation pointing to the book UID for graph traversal — `subject_uid` is the direct reference, the relation carries the graph edge. One `log` per reading — create a new one for re-reads.
- **Library container** → a `topic` node titled "Library"; book assets use `belongs-to` → Library. Shelf subtopics (e.g. "To Read", "Philosophy") are optional children of Library linked the same way.

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

---

## has_asset Field (Location Refactor — Phase 5 complete)

> **Status:** fully live. Schema, resolver infrastructure, all canonical scheme docs, and production
> migration (asset-registry → has_asset frontmatter) are all complete. `local` and `url` schemes
> resolve content directly. All other schemes are pointer-only — Loci stores the location; access
> happens via the appropriate MCP or native tool. The legacy `has_asset: true` boolean form is no
> longer written; read existing nodes defensively if they pre-date Phase 5.

`has_asset` is an optional frontmatter field that attaches file variants and their
storage locations to a vault node. It replaces the legacy separate asset-registry.

### Structure

```yaml
has_asset:
  - format: pdf           # required: file format identifier
    primary: true         # optional: marks the primary/preferred variant (default false)
    locations:            # required: at least one location entry
      - scheme: local     # required: scheme name — must appear in scheme-dictionary
        path: assets/<uid>.pdf  # scheme-specific required fields
        priority: 1       # optional: lower number = preferred fallback order
      - scheme: s3
        bucket: my-backup
        key: <uid>.pdf
        priority: 2
  - format: html
    locations:
      - scheme: google-drive
        file_id: 1aBcD...
```

**Before writing any has_asset entry:** call `loci__read_meta(file="scheme-dictionary")`
to confirm valid scheme names and their required fields. Unknown schemes and missing
required fields are lint errors.

**Authoritative fields only** — store only what cannot be derived: format, primary flag,
scheme, scheme-specific identifiers, priority. Do NOT store mime_type, size_bytes,
last_verified_at, or registered_at — these are computed at resolve time.

### Scheme model

Each location's `scheme` names a storage type. The scheme determines which resolver
handles the location and which fields are required. Current canonical schemes:

| Scheme | Required fields | enumerate? |
|---|---|---|
| `local` | `path` | yes |
| `google-drive` | `file_id` | yes |
| `nextcloud` | `path` | yes |
| `onedrive` | `item_id` | no |
| `dropbox` | `path` | no |
| `icloud-drive` | `path` | no |
| `url` | `url` | no |
| `gmail` | `thread_id`, `message_id` | yes |
| `s3` | `bucket`, `key` | yes |
| `ssh-remote` | `host`, `path` | yes |

User-defined schemes go in scheme-dictionary-user. They must not collide with canonical names.

### Two relationships to content

- **Adopt** — file lives under `loci/assets/`. Vault is canonical. Use `scheme: local`
  with `path: assets/<uid>.<format>`.
- **Reference** — file lives elsewhere (Drive, Gmail, URL, etc.). Vault carries a pointer;
  the original remains canonical. Use the appropriate non-local scheme.

A single variant can mix both — a local copy as primary, a cloud mirror as fallback.

### find_nodes filters

`loci__find_nodes` now accepts:
- `has_asset=True` — return only nodes with an asset attached (either form)
- `has_asset_scheme="google-drive"` — return only nodes with a location using that scheme

### Scheme: url

Use `scheme: url` to reference a specific web resource by its HTTP/HTTPS address. Suitable for web pages, downloadable files, publicly accessible PDFs, API endpoints, or any single resource reachable via a URL.

**When to use:** the content lives at a stable URL you want to record as the canonical location. Contrast with `source_url` (which is a vault frontmatter field for the *origin* of the content), and with bookmarks (vault nodes whose *subject* is a URL). Use `has_asset` with `scheme: url` when you want the URL to be resolvable — i.e. when the system should be able to fetch the content on demand.

**Required field:** `url` — the full `https://` or `http://` URL.

**No enumerate.** A bare URL points to a single resource, not a container. `sync_locations` skips `url` locations silently.

**Example:**

```yaml
has_asset:
  - format: pdf
    primary: true
    locations:
      - scheme: url
        url: https://arxiv.org/pdf/2401.00001
```

**Limitations:**
- No authentication support. Use a different scheme for resources behind OAuth or API keys.
- Resolver respects HTTP redirects and returns the final URL in the result.

> **Note on external schemes (all schemes below):** For non-local, non-URL schemes, Loci stores the location pointer only. It does not fetch content from the service. To access the file, use the appropriate MCP server or native tool for that service (google-docs MCP for Drive/Gmail, native Nextcloud client, AWS CLI for S3, etc.).

### Scheme: google-drive

Use `scheme: google-drive` when the file lives in Google Drive and you want to record its canonical Drive location.

**When to use:** the file is owned or primarily stored in Drive — shared decks, collaborative docs, uploaded attachments. Not needed if the file is already synced locally and `scheme: local` covers it.

**Required field:** `file_id` — the Drive file ID. Find it in the file's URL: `https://drive.google.com/file/d/<file_id>/view`.

**Enumerate:** supported (folder listing). Scope field: `file_id` pointing to a Drive folder ID.

**Example:**
```yaml
has_asset:
  - format: pdf
    primary: true
    locations:
      - scheme: google-drive
        file_id: 1aBcDeFgHiJkLmNoPqRsTuVwXyZ
```

### Scheme: nextcloud

Use `scheme: nextcloud` for files on a Nextcloud server accessed via WebDAV.

**When to use:** the file lives on a Nextcloud instance and you want to reference it by server path — especially useful when the file is not synced locally on all devices.

**Required field:** `path` — path relative to the user's Nextcloud root (e.g. `Documents/report.pdf`).

**Optional field:** `host` — Nextcloud server base URL (e.g. `https://cloud.example.com`). If omitted, the resolver falls back to the `NEXTCLOUD_HOST` environment variable.

**Enumerate:** supported (WebDAV directory listing). Scope fields: `path`, optional `host`.

**Example:**
```yaml
has_asset:
  - format: pdf
    locations:
      - scheme: nextcloud
        path: loci/assets/report.pdf
        host: https://cloud.example.com
```

### Scheme: gmail

Use `scheme: gmail` when the vault node represents a Gmail message — e.g. an important email thread saved as a reference.

**When to use:** the *content itself* is an email (not just a link to one). Both `thread_id` and `message_id` are required so the message can be uniquely located.

**Required fields:** `thread_id` and `message_id`. Find them in the Gmail URL: `https://mail.google.com/mail/u/0/#inbox/<thread_id>`, or via the Gmail API.

**Enumerate:** supported (label listing). Scope field: `label_id` (e.g. `"INBOX"` or a custom label ID).

**Example:**
```yaml
has_asset:
  - format: message
    primary: true
    locations:
      - scheme: gmail
        thread_id: 18f3a2b1c0d4e5f6
        message_id: 18f3a2b1c0d4e5f6
```

### Scheme: icloud-drive

Use `scheme: icloud-drive` for files in iCloud Drive, referenced by their local sync path.

**When to use:** the file is in iCloud Drive and synced to the local filesystem. The path is device-specific (where iCloud syncs on that machine). If the file is reliably present locally, `scheme: local` with the synced path works too — `icloud-drive` signals the semantic intent that this is iCloud-managed content.

**Required field:** `path` — absolute or `~`-relative path to the iCloud-synced file (e.g. `~/Library/Mobile Documents/com~apple~CloudDocs/Documents/file.pdf`).

**No enumerate.**

**Example:**
```yaml
has_asset:
  - format: pdf
    locations:
      - scheme: icloud-drive
        path: ~/Library/Mobile Documents/com~apple~CloudDocs/Papers/paper.pdf
```

### Scheme: onedrive

Use `scheme: onedrive` for files in Microsoft OneDrive, identified by their Microsoft Graph item ID.

**When to use:** the file is owned in OneDrive and you want to record its canonical location by Graph item ID (stable across renames and moves).

**Required field:** `item_id` — Microsoft Graph Drive item ID. Retrieve it via the Graph API or from the OneDrive sharing URL parameters.

**No enumerate.**

**Example:**
```yaml
has_asset:
  - format: docx
    locations:
      - scheme: onedrive
        item_id: 01ABCDEFGHIJKLMNOPQRST
```

### Scheme: dropbox

Use `scheme: dropbox` for files in Dropbox, identified by their Dropbox path.

**When to use:** the file lives in Dropbox and you want the canonical Dropbox path recorded. The path is stable as long as the file isn't moved within Dropbox.

**Required field:** `path` — Dropbox path starting with `/` (e.g. `/Documents/report.pdf`).

**No enumerate.**

**Example:**
```yaml
has_asset:
  - format: pdf
    locations:
      - scheme: dropbox
        path: /Research/papers/2024/paper.pdf
```

### Scheme: s3

Use `scheme: s3` for objects in AWS S3.

**When to use:** the file is stored in S3 — uploaded artifacts, large binaries, backups. Both `bucket` and `key` are required.

**Required fields:** `bucket` and `key`.

**Optional field:** `region` — AWS region (e.g. `us-east-1`). Omit to use the default from the AWS credential chain.

**Enumerate:** supported (prefix listing). Scope fields: `bucket`, optional `key` as prefix.

**Example:**
```yaml
has_asset:
  - format: zip
    locations:
      - scheme: s3
        bucket: my-artifacts
        key: builds/2024-05-01/release.zip
        region: us-west-2
```

### Scheme: ssh-remote

Use `scheme: ssh-remote` for files on a remote server accessible via SSH.

**When to use:** the file lives on a server you access by SSH — build outputs, logs, data files on a remote machine. Auth is via the system SSH agent and default key files; no credentials are stored in Loci.

**Required fields:** `host` and `path` (absolute path on the remote host).

**Optional fields:** `user` (SSH username; defaults to current user) and `port` (defaults to 22).

**Enumerate:** supported (remote `ls`). Scope fields: `host`, `path`, optional `user` and `port`.

**Example:**
```yaml
has_asset:
  - format: log
    locations:
      - scheme: ssh-remote
        host: build-server.example.com
        path: /var/log/build/output.log
        user: ci
```
