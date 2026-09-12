---
name: loci-ingest-directory
description: >
  Scan a directory and create vault nodes for any files that don't already
  have one. Use when the user wants to register files from an arbitrary
  directory into the knowledge vault — e.g. "ingest my Documents folder",
  "create vault nodes for files in ~/projects/reports", "register everything
  in this directory". No assumptions are made: each file gets its own node,
  and the user is shown what will be created before anything is written.
---

# Loci Ingest Directory Skill

Creates vault nodes for files in a given directory that don't already have one,
using `has_asset` frontmatter with `scheme: local`.

---

## Step 1 — Confirm the directory

Ask the user for the directory path if not already provided. Confirm:
- The exact path (expand `~` to full path if needed)
- Whether to scan subdirectories recursively (default: no)

---

## Step 2 — Scan

Call `loci__scan_directory(path=<directory>, recursive=<bool>)`.

If the result contains an `"error"` key, report it and stop.

Show the user:
- Total files found
- Count already registered (with vault nodes) — list their filenames and node UIDs
- Count unregistered — list their filenames, detected formats, and the `suggested_type`
  (with `suggested_subtype` where set) the scan proposes for each

If all files are already registered, report that and stop.

If there are unregistered files, ask the user to confirm before proceeding:
> "Found N unregistered files. Create vault nodes for all of them?"

Wait for confirmation before continuing.

---

## Step 3 — Read ontology and scheme dictionary

Call `loci__read_meta(file="ontology")` — this is the schema source of truth for required fields,
optional fields, and valid enum values for the types you will write (`document`, `asset`).

Call `loci__read_meta(file="scheme-dictionary")` — confirms valid scheme names and required fields.
Verify that `local` requires `path` and that no unknown schemes are used.

---

## Step 4 — Create nodes (one per unregistered file)

For each file in `unregistered`:

### 4a — Derive metadata

- **title**: the scan's `suggested_title` (the humanized filename), unless the user corrected it
- **format**: the scan's `format` field (file extension without the dot)
- **type**: the scan's `suggested_type` and `suggested_subtype` — ebooks are `asset` /
  `book`, everything else `document`. Override only when the user says the suggestion is wrong.
- **summary**: one sentence describing what the file is, based on its name, format, and directory context.
  Don't fabricate content — describe what can be inferred from the filename and format only.
- **tags**: 2–4 lowercase hyphenated tags derived from filename and format.
- **domains**: infer from directory context and filename. If unclear, omit or use `technology-engineering`.

### 4b — Write the node

Call `loci__generate_uid` to get a UID.

Call `loci__write_vault` with:
```
type:    <type>
title:   <title>
summary: <summary>
tags:    <tags>
domains: <domains>
body:    "# <title>\n"
extra_fields:
  uid: <uid from generate_uid>
  has_asset:
    - format: <format>
      primary: true
      locations:
        - scheme: local
          path: <absolute path from scan result>
```

For `asset` type nodes, also include in `extra_fields`:
```
  subtype: book
  storage: digital
```

`write_vault` checks for duplicates itself. If it returns `duplicate: true`, nothing was
written: show the user the title and the existing node's path and ask whether to skip this file
or create a second node anyway (call again with `allow_duplicate=true`). Wait for the answer
before moving on to the next file.

---

## Wrap-up

After processing all files:

1. Show a summary: N nodes created (titles and UIDs), M files skipped (filenames and reasons).
2. Surface anything the tools returned that the user should know — write warnings, a `_notice`
   from the reachability check — in one line each.
3. Offer the one follow-on that fits: scanning a sibling directory, or a `loci__lint_vault` run
   over the new nodes.

---

## 🔒 Rules

- **Never guess on ambiguous filenames.** If the type or title is genuinely unclear, ask the user.
- **Always show the scan result before writing anything.** The user must confirm.
- **One node per file.** Do not merge multiple files into one node.
- **Store the path as-is from the scan result** (absolute path). Do not make it relative unless the file is inside the loci root.
- **Do not ingest hidden files** (starting with `.`) — the scanner already excludes them.
