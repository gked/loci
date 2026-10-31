---
name: loci-save
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

## 🔒 Ground rule

**When in doubt, ask. Never guess on anything that requires user intent.**

This applies everywhere in the workflow: type classification, project or entity linkage,
duplicate resolution, ambiguous matches. If there are multiple candidates, surface them
and let the user choose. One focused question is better than a wrong assumption.

---

## Save Workflow

### 🔒 Step 0 — Verify the vault is reachable

Call `loci__list_vault` with no arguments. If it errors, relay the error text verbatim — it says
what is wrong and what to do — and stop; on `LOCI_NOT_CONFIGURED`, ask the user where the vault
should live (never guess a path or offer a default) and call `loci__set_vault_root`.

If the result has a `_notice` key: if it mentions lint errors, ask before continuing —
"FYI: vault linter reports N errors (likely ontology drift). Want me to generate fix instructions
first? [yes / continue with save]" — otherwise show it as a one-line FYI. Don't auto-fix.

---

### Step 1 — Classify the content

If the type is not obvious, call `loci__read_meta(file="type-dictionary")` and
`loci__read_meta(file="type-decision")`. When it is unambiguous (the user said "save this URL",
or named a type), skip these. If unsure between two types, ask — type affects frontmatter fields.

**URL rule:** a bare URL, with or without commentary, defaults to `bookmark`. Use `article` only
when the user asks to capture, summarise, or pull the content. When in doubt: "Save as a bookmark,
or pull the full content as an article?" For a `bookmark`, call `loci__fetch_url_metadata(url)`
immediately and use the result for title, site_name, and summary — ask only if the fetch fails.
**The URL goes in `extra_fields.source_url` (required) — that is the field the duplicate check
reads, so a URL passed anywhere else is not checked.**

**Set the `subtype` field (required where the type has one; never duplicate it as a tag):**
- `task` → `bug` (something is broken) | `feature` (something to build — default) |
  `question` ("Decide…", "Investigate…", "Think through…", open questions) | `chore` (admin)
- `document` → `meeting-notes` | `report` (findings, snapshots, readouts) | `spec` | `plan`
  (incl. playbooks) | `transcript` | `essay` (for a reader, has a thesis) | `journal` |
  `note` (for yourself, open-ended — default)
- `article` → the medium: `article` | `blog-post` | `news` | `book` | `paper` | `scholarly` |
  `technical` | `video`
- `entity` → `person` | `organization` | `place`
- `asset` → `book` | `video` | `music` | `podcast` | `presentation` | `visual` | `physical`
- `procedure` → no subtype yet; tag the category: #recipe, #workout, #protocol, #playbook, #tutorial
- `skill` → a reusable agent skill (extends `procedure`; no subtype). Use it, not `procedure`, for a SKILL.md-style workflow

A subtype never encodes who it was with or which sphere it belongs to — that is an
`involves` / `belongs-to` relation and `domains`. Before adding any tag, ask: does it name
another node (→ relation)? Is it the subtype? Only then is it a tag. Call
`loci__read_meta(file="type-decision")` when the subtype is not obvious.

**Binary file / media (video, audio, image, PDF, ebook):** use `loci__save_asset`, not
`loci__write_vault`. It writes the file to `loci/assets/` and creates the proxy node in one
crash-safe sequence. Pick the path by where the bytes are:

1. **File on disk** — `loci__save_asset(source_path=<absolute path>, ...)`. No size limit; always
   the most reliable path.
2. **Dropped into the conversation and small** (images, PDFs up to a few hundred KB, text Claude
   generated) — `loci__save_asset(content=<content>, is_base64=<bool>, ...)`.
3. **Dropped into the conversation and large** (video, audio, raw images, anything truncated or
   said to be large) — don't attempt inline. Tell the user: "This file is too large to save
   directly from the conversation. Please drop it into your `loci-stage/` folder, then ask me to
   run the inbox scan." Then the inbox skill takes over.

**Never** base64-encode a file yourself. Set `node_type` (`asset` for media the user owns,
`document` for a PDF or file that is written content) and the `subtype` from the lists in
Step 1 — `video`, `music`, `book`, `visual`, … for an asset; `report`, `transcript`, … for a
document (`note` when omitted). `save_asset` returns `{uid, asset_path, vault_path}` —
confirm all three to the user. It checks for duplicates the same way `write_vault` does (Step 4):
on `duplicate: true` nothing was written; ask, and retry with `allow_duplicate=true` for "new".

**Books:**
- An ebook or book the user owns → `asset`, `subtype: book` (no `#book` tag — the subtype is the query key). Call
  `loci__read_meta(file="field-dictionary")` for the body template, summary convention, and genre
  list. `genre` is required — exactly one canonical slug; if ambiguous, pick the closest and note
  it in the body. Body sections: `## Bibliographic`, `## About`, `## Notes`.
- Non-English books override the English-only summary rule: English paragraph first, native
  language second.
- A reading → `log`. Required: `subject_uid` (the book's UID), `log_status`
  (in-progress | finished | abandoned), tag `reading`, plus an `about` relation to the book. One
  log per reading — re-reads get a new one.
- Library container → a `topic` titled "Library"; books use `belongs-to` → Library. Shelf
  subtopics ("To Read", "Philosophy") are optional children linked the same way.

---

### Step 2 — Generate frontmatter

Call `loci__generate_uid` for the UID.

**Always** call `loci__read_meta(file="ontology")` before writing. It is the schema source of
truth — required fields, optional fields, enum values. Skipping it causes silent write failures.

Read these **only when needed**:
- `tag-dictionary` — when tags matter for findability; prefer existing tags over synonyms, and
  add new recurrent tags via `loci__write_meta` first.
- `field-dictionary` — for complex objects (`relations`, `references`, entity archiving,
  temporal fields). Not a source for required/optional status or enums — that is ontology.
- `relation-dictionary` and `relation-dictionary-user` — when choosing a non-default relation;
  pick the most specific type rather than defaulting to `relates-to`.
- `has-asset-guide` — before writing any `has_asset` entry (a node that points at a file rather
  than adopting it). Follow it for scheme choice and required fields.

**User-defined types:** if the requested type is not canonical, call
`loci__read_meta(file="ontology-user")`. If it is registered there, proceed. If not, ask which
canonical type it extends, confirm the description, and call
`loci__define_type(name=, extends=, description=)`; surface errors, then proceed.

**User-defined relations:** if the relation name is in neither dictionary, confirm the
description (optionally a group and inverse) and call `loci__define_relation(name=, description=)`
with `group` / `inverse_of` if given. Every relation needs an inverse or `symmetric=true`
(its own inverse); lint warns otherwise. Use it immediately on success; treat warnings as
informational.

**Language and aliases:**
- `summary` is **always English** — it is the search bridge. `title` is the canonical name in the
  content's original language. Set `language: <ISO 639-1>` only when the body is not English.
- When `title` or an entity name is non-English, populate `aliases` with the English
  transliteration or translation; add common abbreviations and alternate spellings too.
  ```yaml
  title: Маркеев Олег
  aliases:
    - Oleg Markeev
  ```

**Relations and references:**
```yaml
relations:
  - uid: b7d4e1a2
    type: influences
references:
  - url: https://example.com
    title: The Article Title
    source_type: article
```
For `depends-on` / `enables`, store one direction only — `depends-on` on the dependent node.

---

### Step 3 — Resolve mentions and link

**Do this for every save.** Content almost always names things the vault already knows — the
people in a meeting, the project a task belongs to, the organisation an article is about — and a
node saved without those links is a node the graph cannot find later.

1. Pull out every proper name in the content and its context: people, organisations, places,
   projects, topics, products. Include the user's own project if the content is clearly about it.
2. Call `loci__resolve_mentions(names=[...])` once with all of them.
3. Present every hit together in one prompt — never one at a time:
   ```
   This looks related to:
     • Entity: John Smith (a1b2c3d4) — link it? [yes / no]
     • Project: Loci (partial match on "Loci — knowledge vault") — link it? [yes / no]
     • Acme Corp — not in the vault. Create an entity node? [yes / no]
   ```
   A name that resolved to several nodes: show them and ask which. A `partial` hit is a
   candidate, not a match — say so. Offer to create a node for a `missing` name only when it is
   the kind of thing worth a node (a person or organisation the user will meet again, a project),
   not for every noun.
4. On confirmation, add the UID to `relations` with the most specific relation type that fits.
   On "create", save that node first, then link back. **Do not auto-link without confirmation.**

**Topics:** when saving a `topic` with a `parent_topic`, resolve the parent through the same
call. One hit → use its UID and add a `child-of` relation. Several → ask which. None → ask
whether to create it first or save without a parent. After the save, offer: "Want me to scan
existing vault content for items to link to this topic?" — on yes, `loci__search_vault` for the
title, present candidates grouped by type, and patch the topic with the confirmed links.

---

### 🔒 Step 4 — Confirm and write

Call `loci__read_meta(file="config")` for `vault_root` and show the intended location:

```
Save to: <vault_root>/<generated-filename>
Proceed? [yes / no / change location]
```

Do not write until the user confirms. Then call `loci__write_vault` with all assembled fields.

`write_vault` checks for duplicates itself. If it returns `duplicate: true`, nothing was
written — the result names the existing node. Ask:
```
A similar item already exists: <name>
Save as a new item, or update the existing one?
```
"New" → call `loci__write_vault` again with `allow_duplicate=true`. "Update" → switch to the
update workflow (below) for that node.

---

### Step 5 — Foreign content schema discovery

If the content comes from an external app (Jira, calendar, email, Slack, …), call
`loci__read_meta(file="foreign-definitions")`. If there is no schema for that source yet, ask:
"This looks like content from [source]. I don't have a schema for it yet. What metadata matters to
you from this source? Available fields: [list]". Confirm, then
`loci__write_meta(file="foreign-definitions", content=<updated content>)`.

---

### Wrap-up

Every save ends here, whichever path it took.

1. Report the result in this shape:
   ```
   Saved: <full_path>
   UID: <uid>
   Type: <type>
   Links: <count>
   ```
2. Surface anything the tools returned that the user should know — `body_warnings`,
   `relation_warnings`, `has_asset_warnings`, `field_warnings` (from a patch), lint notices,
   a `_notice` deferred from Step 0 — in one line each. Don't act on them unasked.
3. `tag_warnings` is the exception: the write went through, but a tag has a better home — it
   names a project, entity, or topic (should be a relation) or repeats the node's own type or
   subtype. Offer the fix in one line and do it on a yes, never before:
   ```
   Tag #mercury names project Mercury — replace it with a belongs-to edge? [yes / keep the tag]
   ```
   On yes, `loci__patch_vault(path=<uid>, updates={relations: <existing + new edge>, tags: <without it>})`.
   When the warning says the node *already links to* that target, or the tag repeats the type,
   there is no edge to add — the offer is to drop the tag, and on yes the patch is `tags` only.
4. Offer the one follow-on that fits: the topic link scan from Step 3, creating a node for a
   `missing` mention the user skipped, or reading the saved node back. One offer, not a menu.

---

## Updating an existing node

For "update X", "add a link to Y", "mark that task done", "archive Z", deletions, or when Step 4
found a duplicate the user wants to update: call `loci__read_meta(file="update-workflow")` and
follow it. Its rules matter — patch replaces whole fields, `body` is a separate argument, entity
temporal fields archive the old value before changing — so read it rather than working from
memory.

---

## 🔒 Recovering from a mistake

Every vault write is a commit. If a write removed or overwrote content by
mistake — a patch that dropped a field or the body, a delete that was wrong —
repair it yourself instead of asking the user to redo the work:

1. `loci__history_vault(path=<uid>)` — find the commit. A deleted node is found
   by its UID too.
2. `loci__diff_vault(path=<uid>, commit=<hash>)` — see what that commit changed.
   `loci__read_vault(path=<uid>, commit=<hash>)` reads the version from before
   the mistake (`<hash>~1` for the commit that deleted it). Check it holds what
   you want back.
3. If the bad commit is the newest one for the node in the list from step 1,
   nothing changed after it: `loci__restore_vault(path=<uid>, commit=<hash>~1)`.
   A restore puts the node back as it was right after the commit you name, so
   name the one before the mistake, not the bad one.
   Right after your own bad write, `loci__undo_last_vault_change(commit=<hash>)`
   does the same, with the hash the write returned. It refuses when a newer
   change landed, or when the newest commit holds edits made outside Loci.
   If the bad commit created the node, `<hash>~1` holds no version of it, so a
   restore fails. Remove a node created by mistake with `loci__delete_vault`
   or `loci__undo_last_vault_change`.
4. If the node changed after the mistake, a restore would drop those changes.
   Ask the user, or patch only the missing part back with `loci__patch_vault`.
5. Tell the user what you restored: which node, which commit, and why.

A restore is a new commit, so it loses nothing and can be undone.

---

## Edge cases

- **No clear title:** generate from the first sentence or ask. Never leave it blank.
- **Unknown type:** `article` if there is a citable source (URL, author, publication);
  `document` if there is no publication record to track. Ask only when genuinely ambiguous.
- **Very long content:** summarise in `summary`, keep the full content in the body.
