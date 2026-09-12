---
name: loci-inbox
description: >
  Process the loci-stage inbox: scan staged files, present a plan to the user,
  then execute file ingestion and content processing in batches. Use whenever
  the user says "process my inbox", "clean up staging", "ingest staged files",
  or "what's in my inbox".
---

# Loci Inbox Skill

Processes loci-stage/ into the vault in two phases: analysis then execution.

---

## 🔒 Step 0 — Check vault reachability

Call `loci__list_vault` with no arguments. If it errors, relay the error text verbatim — it says
what is wrong and what to do — and stop; on `LOCI_NOT_CONFIGURED`, ask the user where the vault
should live (never guess a path or offer a default) and call `loci__set_vault_root`.

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
  ≈  1 already in vault: dune.epub — matches "Dune" (a1b2c3d4)
  → 193 remaining (~4 runs left)

Continue with another file batch? [yes / switch to content / stop]
```

Items under `duplicates` were not saved — the vault already has a node with that title. Their
staging files are kept and the plan parks them as `duplicate`, which keeps the plan open until
the user decides. For each, ask: skip it → `loci__update_inbox_item(path=..., status="skipped")`;
or save a second copy → `loci__update_inbox_item(path=..., status="pending", allow_duplicate=true)`
and the next file batch saves it. Never re-queue without asking.

### Content batch (Claude-assisted)

Call `loci__get_inbox_content_batch()`.

For each item returned:
1. Read the content
2. Classify (type, tags, summary) using loci-save skill logic (Steps 1-2 of loci-save)
3. Call `loci__resolve_mentions` with the names in the content and link confirmed hits
   (loci-save Step 3) — batch the questions for the whole batch into one prompt
4. Call `loci__write_vault` to save the node. If it returns `duplicate: true`, nothing was
   written: ask whether to update the existing node or save anyway (`allow_duplicate=true`)
5. Call `loci__update_inbox_item(path=..., status="done", uid=<uid>)`

Present a summary after each batch:
```
Content batch complete:
  ✓ 10 items processed
  → 34 remaining (~4 runs left)

Continue with another content batch? [yes / switch to files / stop]
```

---

## Wrap-up

Every session ends here, whether the user stopped after one batch or the plan reached `done`.

1. Show the running totals: processed, failed (with the errors), parked as duplicate (with the
   existing node each matched), remaining, and the estimated runs left.
2. Surface anything the tools returned that the user should know — write warnings, a `_notice`
   from Step 0 — in one line each.
3. Offer the one follow-on that fits: the next batch of the same kind, switching to the other
   pass, or — when the plan is done — a `loci__lint_vault` run over what was ingested.

---

## 🔒 General rules

- Never execute without an approved plan.
- Always show batch results before offering to continue — never auto-chain without user confirmation.
- If a file batch has >20% failures, stop and surface errors before continuing.
- Content items: use the same classification rules as loci-save skill Step 1.
- If vault is unreachable mid-execution, stop immediately and tell user to check the server.
