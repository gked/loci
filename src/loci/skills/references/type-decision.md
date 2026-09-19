# Type Classification Guide
# Read by the save skill at Step 1.
# Answers: what type is this content, and what subtype applies.
#
# STRUCTURAL AUTHORITY: ontology.yaml
# The canonical list of valid types, their required fields, and enum values
# are defined in ontology.yaml. This file only explains when to use each type.
# If a type named here is not in ontology.yaml, it does not exist.

## Core rule

A separate type is justified only when variants have different required fields.
Distinctions within a type are a subtype when they form a closed, exclusive list, and a tag otherwise. Neither justifies a new type.

---

## Decision tree

Work through these questions in order. Stop at the first match.

**1. Is the content just a URL the user wants to save without extracting it?**
→ `bookmark`

**2. Is the content a file stored in the asset vault, or a physical object the user owns?**
→ `asset` — set `subtype` (book | video | music | podcast | presentation | visual | physical) and `storage` (digital | physical | both)
Note: a book you are reading or have read is `article subtype: book`, not `asset`. An ebook file you own, or a physical book on your shelf, is `asset subtype: book`.

**3. Does the content have a citable source?**
A citable source means: a URL where it was published, an identifiable author, or a publication date.
→ Yes: `article`
→ No: `document`

**4. Is the content a structured sequence of steps with an expected outcome?**
→ `procedure`

**5. Is the content about a real-world actor — a person, organization, or place?**
→ `entity` — set the `subtype` field (person | organization | place); do NOT add subtype as a tag

**6. Is the content an ongoing effort with goals and milestones?**
→ `project`

**7. Is the content a discrete actionable item?**
→ `task`

**8. Is the content a point-in-time or period occurrence?**
→ `event`

**9. Is the content a saved conversation (LLM or human)?**
→ `conversation`

**10. Is the content an organizing hub for a subject area with no content of its own?**
→ `topic`
Deciding between topic and tag: if you'd want to navigate *to* this subject and see what's linked, use `topic`. If you'd use it only as a filter label on other content, use a tag. A topic that ends up with no relations is probably better as a tag.

**When to ask:** if two types still seem equally valid after applying these rules, ask the user. Do not guess — type determines which fields are collected.

---

## Subtype by type

After determining the type, set the `subtype` field where the type has one.
A subtype is a closed, mutually exclusive partition of the type: every node of
that type picks exactly one, and the linter rejects anything outside the list.

| Type | `subtype` (pick one) |
|---|---|
| `task` | `bug` — something is broken · `feature` — something to build (default) · `question` — something to decide or find out ("Decide…", "Investigate…", "Think through…", open questions) · `chore` — admin with no product outcome |
| `document` | `meeting-notes` · `report` (findings, snapshots, readouts) · `spec` (design, requirements, architecture) · `plan` (project/dev plans, playbooks) · `transcript` (lesson or recording transcripts) · `essay` · `journal` (personal, dated) · `note` (default) |
| `article` | `article` · `blog-post` · `news` · `book` · `paper` · `scholarly` · `technical` · `video` — the medium of the content |
| `entity` | `person` · `organization` · `place` |
| `asset` | `book` · `video` · `music` · `podcast` · `presentation` · `visual` · `physical` |
| `procedure` | none yet — use a tag for the category: #recipe, #workout, #protocol, #playbook, #tutorial |
| all others | none |

**essay vs note** — the one fuzzy pair. An *essay* is written for a reader
other than you, has a thesis, and is complete or meant to be. A *note* is for
yourself, open-ended, no thesis required. A note later finished into an essay
changes its subtype on the same node — that is an edit, not a new node.

**A subtype never encodes what a relation or `domains` already says.** There is
no `customer-meeting-notes`: it is `subtype: meeting-notes` plus an `involves`
edge to the customer entity plus `domains: [business-strategy]`. Wanting such a
subtype is the signal that the edge is missing.

**Before reaching for a tag, ask in order:**
1. Does the label name another node (a project, a person, a company, a subject)?
   → a **relation** (`belongs-to`, `involves`, `about`).
2. Is it a closed, exclusive, stable partition of the type? → a **subtype**.
3. Otherwise → a **tag**. Tags are open and overlapping; prefer an existing one.
