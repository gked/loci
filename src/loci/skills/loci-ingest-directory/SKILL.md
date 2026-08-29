---
name: loci-ingest-directory
skill_version: 4
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

## Version Check (run before anything else)

This skill is at `skill_version: 4`.

Before following any instructions below:
1. Call `loci__read_skill(skill="loci-ingest-directory")` to fetch the latest version
2. Parse the `skill_version` from its frontmatter
3. If the MCP version is **newer**, follow those instructions instead — ignore the rest of this document
4. If versions match, proceed normally below

If `loci__read_skill` is unavailable, tell the user:
```
The Loci vault is not reachable.
```
Then relay the error text the tool returned verbatim — it names the cause and
the fix for this install (an unmounted path, a missing volume mount, no vault
configured yet). Do not substitute a setup command for it: `setup.py` only
exists in a local checkout, so it is wrong for a Docker or `uvx` install and
fails outright anywhere but that checkout directory. If there is no error text,
the MCP server itself is not connected — tell the user to check their MCP
client config and restart Claude Code / Claude Desktop.
Do not proceed.

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
- Count unregistered — list their filenames and detected formats

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

- **title**: humanize the filename — strip extension, replace `_` and `-` with spaces, title-case.
  E.g. `my_report_2024.pdf` → `My Report 2024`
- **format**: from the `format` field in the scan result (file extension without the dot)
- **type**: pick the most appropriate vault node type:
  - `.epub`, `.mobi`, `.azw`, `.azw3` → `asset` with `subtype: book`
  - `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.xlsx`, `.xls`, `.txt`, `.rtf`, `.odt` → `document`
  - `.md`, `.markdown` → `document`
  - `.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a`, `.aac` → `document` (audio)
  - `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` → `document` (video)
  - `.jpg`, `.jpeg`, `.png`, `.gif`, `.svg`, `.webp`, `.bmp`, `.tiff` → `document` (image)
  - Anything else → `document`
- **summary**: one sentence describing what the file is, based on its name, format, and directory context.
  Don't fabricate content — describe what can be inferred from the filename and format only.
- **tags**: 2–4 lowercase hyphenated tags derived from filename and format.
- **domains**: infer from directory context and filename. If unclear, omit or use `technology-engineering`.

### 4b — Duplicate check

Call `loci__check_duplicate(type=<type>, title=<title>)`.

If a duplicate is found:
- Show the user: title, existing node path
- Ask: skip this file, or proceed and create a second node anyway?
- Wait for their answer before continuing with this file.

### 4c — Write the node

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

---

## Step 5 — Report

After processing all files, show a summary:
- N nodes created (list titles and UIDs)
- M files skipped (list filenames and reasons)

---

## Rules

- **Never guess on ambiguous filenames.** If the type or title is genuinely unclear, ask the user.
- **Always show the scan result before writing anything.** The user must confirm.
- **One node per file.** Do not merge multiple files into one node.
- **Store the path as-is from the scan result** (absolute path). Do not make it relative unless the file is inside the loci root.
- **Do not ingest hidden files** (starting with `.`) — the scanner already excludes them.
