# Type Classification Guide
# Read by the save skill at Step 1.
# Answers: what type is this content, and what format tags apply.
#
# STRUCTURAL AUTHORITY: ontology.yaml
# The canonical list of valid types, their required fields, and enum values
# are defined in ontology.yaml. This file only explains when to use each type.
# If a type named here is not in ontology.yaml, it does not exist.

## Core rule

A separate type is justified only when variants have different required fields.
Descriptive differences — format, category, style, domain — belong in tags, not types.

---

## Decision tree

Work through these questions in order. Stop at the first match.

**1. Is the content just a URL the user wants to save without extracting it?**
→ `bookmark`

**2. Does the content have a citable source?**
A citable source means: a URL where it was published, an identifiable author, or a publication date.
→ Yes: `article`
→ No: `document`

**3. Is the content a structured sequence of steps with an expected outcome?**
→ `procedure`

**4. Is the content about a real-world actor — a person, organization, or place?**
→ `entity` — set the `subtype` field (person | organization | place); do NOT add subtype as a tag

**5. Is the content an ongoing effort with goals and milestones?**
→ `project`

**6. Is the content a discrete actionable item?**
→ `task`

**7. Is the content a point-in-time or period occurrence?**
→ `event`

**8. Is the content a saved conversation (LLM or human)?**
→ `conversation`

**9. Is the content an organizing hub for a subject area with no content of its own?**
→ `topic`

**When to ask:** if two types still seem equally valid after applying these rules, ask the user. Do not guess — type determines which fields are collected.

---

## Format tags by type

After determining the type, assign one format tag where it applies:

| Type | Format tags (pick one) |
|---|---|
| `article` | #book, #blog-post, #whitepaper, #research-paper, #news, #magazine, #video, #podcast, #article |
| `document` | #essay, #spec, #design-doc, #meeting-notes, #journal, #note (omit if none fits) |
| `procedure` | #recipe, #workout, #protocol, #playbook, #tutorial |
| `bookmark` | none |
| `entity` | none — use `subtype` field instead |
| all others | none unless a format distinction is meaningful |
