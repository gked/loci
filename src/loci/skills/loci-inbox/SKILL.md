---
name: loci-inbox
skill_version: 4
description: >
  Process the loci-stage inbox: scan staged files, present a plan to the user,
  then execute file ingestion and content processing in batches. Use whenever
  the user says "process my inbox", "clean up staging", "ingest staged files",
  or "what's in my inbox".
---

# Loci Inbox Skill

Processes loci-stage/ into the vault in two phases: analysis then execution.

---

## Version Check

This skill is at `skill_version: 4`.

Before following any instructions:
1. Call `loci__read_skill` with skill="loci-inbox" to fetch the latest version
2. If MCP version is newer, follow those instructions instead
3. If versions match, proceed below

---

## Step 0 — Check vault reachability

Call `loci__list_vault` with no arguments. If it errors, relay the error text
verbatim — it names the cause and the fix for this install — and stop. Do not
substitute a setup command for it: `setup.py` only exists in a local checkout.

---

## Phase 1 — Scan and Present Plan

### Step 1.1 — Check for existing plan

Call `loci__get_inbox_plan()`.

- If `status: approved` or `status: in-progress`: skip to Phase 2 — offer to resume.
- If `status: done`: tell user inbox is empty, show final summary.
- If `status: no-plan` or `status: pending`: proceed with scan.

### Step 1.2 — Scan

Call `loci__scan_inbox()`.

### Step 1.3 — Present to user

Present a summary:

```
Inbox scan complete:
  Files (auto-ingest):   243 ebooks + PDFs → asset nodes (~5 runs of 50)
  Content (manual):       44 notes/articles → document/article nodes (~5 runs of 10)

Estimated: multiple sessions. File ingestion is automatic; content items need
your review per batch.

Approve plan and start? [yes / adjust budget / cancel]
```

### Step 1.4 — Approve

Call `loci__approve_inbox_plan()`.

---

## Phase 2 — Execution

Offer two passes per session: files pass and content pass. User can choose either or both.

### File batch (automated)

Call `loci__execute_inbox_file_batch()`.

Present results:
```
File batch complete:
  ✓ 50 books ingested
  ✗  2 failed: [list errors]
  → 193 remaining (~4 runs left)

Continue with another file batch? [yes / switch to content / stop]
```

### Content batch (Claude-assisted)

Call `loci__get_inbox_content_batch()`.

For each item returned:
1. Read the content
2. Classify (type, tags, summary) using loci-save skill logic (Steps 1-2 of loci-save)
3. Call `loci__write_vault` to save the node
4. Call `loci__update_inbox_item(path=..., status="done", uid=<uid>)`

Present a summary after each batch:
```
Content batch complete:
  ✓ 10 items processed
  → 34 remaining (~4 runs left)

Continue with another content batch? [yes / switch to files / stop]
```

---

## General rules

- Never execute without an approved plan.
- Always show batch results before offering to continue — never auto-chain without user confirmation.
- If a file batch has >20% failures, stop and surface errors before continuing.
- Content items: use the same classification rules as loci-save skill Step 1.
- If vault is unreachable mid-execution, stop immediately and tell user to check the server.
