# The Ontology — How Loci Knows What Things Are

Loci stores everything as plain markdown files. What stops that from becoming a
folder of loose notes is the **ontology**: the small set of rules that says what
kinds of things can exist, what each kind must record, and how they may be
connected.

This is the user's guide. A copy is seeded into your vault at
`meta/ontology-guide.md`, so it's there when you need it. If you're modifying
the code that enforces these rules, read [`ontology-system.md`](https://github.com/gked/loci/blob/main/src/loci/skills/references/ontology-system.md)
instead.

---

## The shape of a note

Every file in your vault has two parts: a **frontmatter** block of structured
fields, and a **body** of free markdown.

```markdown
---
uid: a1b2c3d4
type: article
title: The Bitter Lesson
author: Rich Sutton
state: active
status: null
created_at: '2026-08-10T14:22:03Z'
updated_at: '2026-08-10T14:22:03Z'
archived_at: null
tags: [ai, scaling, essay]
domains: [technology-engineering]
summary: Sutton argues that general methods leveraging computation beat
  hand-crafted domain knowledge over the long run.
relations:
  - uid: 8e8e55de
    type: about
references:
  - url: http://incompleteideas.net/IncIdeas/BitterLesson.html
    title: The Bitter Lesson
    source_type: article
source_url: http://incompleteideas.net/IncIdeas/BitterLesson.html
format: article
---

Full text or your notes go here.
```

The body is yours — write whatever you like. The frontmatter is what the
ontology governs, and it's what makes the vault queryable: "every task due this
week", "everything linked to the Loci project", "all Russian-language books".

---

## Four kinds of thing

Before the types, the idea behind them. Every note stands for something, and
there are only four sorts of something a note can stand for:

| Kind | What it is | Types |
|---|---|---|
| **object** | Exists on its own, persists through time — a person, a company, a place, a copy you own | `entity`, `asset` |
| **information** | Content *about* something, carried by text or a file — written by you or someone else | `document`, `article`, `bookmark`, `conversation`, `procedure`, `log` |
| **occurrent** | Unfolds in time, has a start and an end — happened, or meant to happen | `event`, `task`, `project` |
| **concept** | Has no place or time; exists only to be pointed at | `topic` |

A few placements are worth spelling out, because the obvious answer is wrong:

- A **log** is information, not an occurrent. The reading is what happened; the
  log is your *account* of it — the same family as a document.
- An **asset** is always an object, even when it's an epub. The node stands for
  the copy you own, in whatever medium; `subtype: book` says what the copy
  carries. What you *thought* about the book goes in a log.
- **task** and **project** are occurrents with an *intended* time — a due date
  is a claim about when the thing should end. An event is one that already did.

The kinds aren't a field on the note; nothing in the software reads them. They
are the reason the type list is what it is: one or two concrete types per kind,
and everything else a subtype or a tag. When you're tempted to add a type, place
it in a kind first. If it doesn't fit one, it isn't a type.

---

## Three vocabularies

The ontology is three separate lists, each doing one job.

### 1. Types — what a note *is*

Every note has exactly one `type`. There are twelve:

| Type | Use it for |
|---|---|
| `document` | Something you wrote, with no external source to cite |
| `article` | Something someone else published — blog post, paper, book, news |
| `bookmark` | A URL you want to keep, without capturing the content |
| `conversation` | A saved chat, with an LLM or a person |
| `project` | Ongoing work with goals and milestones |
| `task` | One actionable thing |
| `event` | Something that happened, or will, at a point in time |
| `entity` | A real-world actor — a person, an organisation, or a place |
| `procedure` | A repeatable process with steps and an expected outcome |
| `topic` | A hub for a subject area, so you can navigate *to* it |
| `asset` | Something you own — a file, a physical object, or both |
| `log` | A record of engaging with something over time — a reading, a course |

**The rule for adding a type:** a new type is justified only when it needs
*different required fields*. A `task` and an `event` are genuinely different
types, because one needs a status and the other needs a start time. A bug and
a feature are not — both need exactly what a task needs — so they are
*subtypes* of `task`, not types.

**Subtypes** are a closed list on a type: every task is exactly one of `bug`,
`feature`, `question`, `chore`; every document is exactly one of
`meeting-notes`, `report`, `spec`, `plan`, `transcript`, `essay`, `journal`,
`note`. The list is enforced, so "show me my essays" is trustworthy. A subtype
never says who something was with or which part of your life it belongs to —
relations and domains do that.

Everything looser is a **tag**: open, overlapping, cheap, expected to be a bit
messy. Types stay few and meaningful, subtypes partition them, tags absorb the
rest.

### 2. Relations — how notes connect

Links between notes are typed. Instead of a vague "related", you say *how*:

```yaml
relations:
  - uid: 8e8e55de
    type: belongs-to
```

There are 27 relation types in six groups:

- **Dependency** — `depends-on`, `enables`
- **Structure** — `belongs-to`, `parent-of`, `is-part-of`, `has-part`
- **Provenance** — `is-based-on`, `same-work-as`, `supersedes`, `version-of`,
  `implements`
- **Semantic** — `about`, `mentions`, `influences`, `supports`, `contradicts`,
  `inspired-by`, `informs`, `informed-by`, `references`, `involves`,
  `instance-of`, `used-in`, `uses`
- **Entity** — `works-at`, `follows`
- **Generic** — `relates-to`, for when nothing else fits

Prefer the most specific type that's true. `relates-to` everywhere gives you a
graph that can't answer questions; `contradicts` and `supersedes` give you one
that can.

Every relation has a reverse reading: an inverse (`belongs-to` / `parent-of`,
`supersedes` / `superseded-by`, `about` / `subject-of`) or, for a few, itself
(`relates-to`, `contradicts`, `same-work-as` are symmetric). Record only one
direction. The node at the other end sees the edge as incoming, so there is no
second edge to write — for `depends-on` / `enables`, put `depends-on` on the
note that's blocked. `lint_vault` warns about a relation of yours that names no
inverse and is not symmetric.

### 3. Schemes — where a file actually lives

When a note points at a real file, the `has_asset` field records where it is.
A **scheme** names the kind of place:

```yaml
has_asset:
  - format: pdf
    primary: true
    locations:
      - scheme: local
        path: assets/a1b2c3d4.pdf
      - scheme: google-drive
        file_id: 1aBcDeFgHiJk
```

Available schemes: `local`, `url`, `google-drive`, `nextcloud`, `onedrive`,
`dropbox`, `icloud-drive`, `gmail`, `s3`, `ssh-remote`. Each requires its own
fields — `local` needs a `path`, `s3` needs a `bucket` and `key`, and so on.

A note can list several locations for the same file. That's the point: the vault
records *where things are*, and the same document can be in three places at
once.

---

## Fields every note has

Regardless of type:

| Field | Meaning |
|---|---|
| `uid` | 8-character hex identifier. Permanent. This is how links work. |
| `type` | One of the twelve above |
| `title` | In the content's original language |
| `author` | `self` for your own writing, otherwise the source's author |
| `state` | `active` or `archived` — controls whether it shows up in searches |
| `created_at` / `updated_at` | ISO 8601 timestamps, maintained for you |
| `archived_at` | When you archived it, or `null` |
| `tags` | Freeform lowercase-hyphenated labels |
| `domains` | Broad subject areas, from a fixed list |
| `summary` | One paragraph. **Always in English**, whatever the body's language |
| `relations` | Typed links to other notes |
| `references` | External URLs this note cites |

Optionally: `language` (only when the body isn't English), `aliases`
(translations, transliterations, abbreviations), `has_asset`.

Then each type adds its own. A `task` requires `status` and `subtype`; an
`article` requires `source_url` and `subtype`; an `entity` requires `subtype`.
Some fields are **enums** — a fixed set of allowed values. A task's status can
only be `todo`, `in-progress`, `done`, `cancelled`, or `duplicate`. Anything
else is rejected.

### `state` vs `status` — a distinction worth learning

They're different, and both exist on purpose.

- **`state`** is about *visibility*. `archived` notes disappear from searches and
  graph queries until you explicitly ask for them.
- **`status`** is about *workflow*, and it means something different per type.
  A task's `done` is not a project's `completed`.

A finished task can stay `state: active` — visible, just done. Archive it when
it's no longer relevant to look at, not merely because it's complete.

---

## Tags vs. types vs. topics

Four ways to categorise, easy to confuse:

- **Type** — what the thing fundamentally *is*. One per note. Changes which
  fields you must fill in.
- **Subtype** — which kind, within the type. One per note, from a fixed list.
  Enforced, so you can rely on it.
- **Topic** — a note in its own right, representing a subject. Use one when you
  want to navigate *to* the subject and see everything linked to it.
- **Tag** — a label for filtering. Many per note. Costs nothing. Use freely, but
  prefer an existing tag over inventing a synonym.

Before adding a tag, ask in order: does the label name another note (a project,
a person, a subject)? Then it's a **relation**, not a tag. Is it one of a fixed,
exclusive set within the type? Then it's the **subtype**. Only if neither is it
a tag. Most tag sprawl comes from skipping the first question — a project's
name as a tag on fifty notes is fifty strings the graph can't see, where one
`belongs-to` edge each would do.

A good tag passes one more test: it makes sense on notes in unrelated parts of
the vault. `quantitative` fits a survey readout and a pipeline eval;
`kernel-research` only ever meant one project, so it became an edge. And a tag
never repeats what an edge already says — there is no `product-brainstorming`,
only `brainstorm` on a note that is `about` Product Management.

Loci checks this as you go. Saving a note whose tag names a project, entity, or
topic — or repeats the note's own type or subtype — comes back with a
`tag_warnings` line, and Claude offers the edge instead. The linter reports the
same across the whole vault, plus spellings that differ only by a hyphen or a
plural (`open-question` / `open-questions`) and a census of tags used once.

---

## How notes go stale

Old isn't stale. A note from a year ago with nothing newer on its subject is
still the current state of what you know. A note is **stale** when a *newer*
note on the same subject exists and the two were never linked — the older one
should say "superseded by …" and doesn't.

Today the fix is yours to make: add a `supersedes` edge from the newer note to
the older one when you save it, and the older note is marked as replaced.

> **Not built yet.** The plan is for Loci to treat staleness as a question for
> you, not a rule for the software: look for pairs that could be old-and-new
> versions of one thing — same type and subtype, same subject or project,
> similar title — and ask, per pair, whether the newer one **replaces** the
> older, whether they are **a series** (two biweekly updates, both still
> valid), or **unrelated**. Your answer would be written down, so the same pair
> is never asked twice; *replace* would add the `supersedes` edge, *series*
> would put both under a hub. Nothing detects pairs or asks today.

The one thing that *is* about dates: a task or project past its due date and
untouched is **neglected**. That's a different problem with a different fix, and
it never applies to documents. (Not built yet either — nothing reports it.)

---

## Making it your own

The canonical vocabularies are maintained with Loci and get updated when you
upgrade. You can't edit them — your changes would be overwritten. Instead, each
one has a companion "user" file in `<your-vault>/meta/` that is **yours** and is
never touched by upgrades:

| Yours to edit | Extends |
|---|---|
| `ontology-user.yaml` | types |
| `relation-dictionary-user.yaml` | relations |
| `scheme-dictionary-user.yaml` | schemes |
| `tag-dictionary.md` | tags |

### Adding a type

Ask Claude: *"I want a `recipe` type that extends `procedure`, with `servings`
and `cuisine` fields."* It'll validate and register it.

Three rules constrain what you can define:

1. **Your type must extend a canonical one.** No brand-new roots. This keeps the
   hierarchy exactly one level deep, so every note remains recognisable as one
   of the twelve base types.
2. **The name must not collide** with a canonical type.
3. **Additive only** — you can add fields, never redefine or remove inherited
   ones.

Your type inherits every field of its parent and adds yours on top. A `recipe`
still requires `steps`, because a `procedure` does.

Before you define one, ask whether tags would do. A `recipe` type earns its keep
only if it genuinely needs `servings` as a structured, queryable field. If you
just want to *find* your recipes, a `#recipe` tag on a `procedure` is better.

### Adding a relation or scheme

Same idea, same rules: no collisions with canonical names, additive only. Ask
Claude to define it and it's usable immediately.

---

## When rules are enforced

Deliberately not all at once:

- **Creating a note** is strict. Unknown type, missing required field, or an
  invalid enum value — the write is rejected and you're told why.
- **Editing a note** is permissive. Corrections shouldn't be blocked by rules
  about fields you aren't touching.
- **Linting** is the safety net. `lint_vault` checks the whole vault and reports
  everything: unknown types, missing fields, bad enum values, links pointing at
  notes that no longer exist, notes with no links at all, empty summaries, tags
  that should be edges or repeat the type, and tag spellings that collide.
- **Tag problems warn instead of rejecting.** The note is
  written; the warning says a tag has a better home. That's deliberate — tags
  are the loose axis, and a save should never fail over one.

The third one matters more than it sounds. The ontology evolves — a field
becomes required, an enum gains a value — and notes written last year can fall
out of compliance without anyone touching them. That's **ontology drift**, and
the linter is how you find it. Claude surfaces the count when you save something
and offers to help fix it.

---

## Language handling

The vault is multilingual by design, with one firm rule: **`summary` is always
in English.** It's the bridge that makes everything findable from one search
language.

- `title` stays in the original language — `Чёрная луна`, not `Black Moon`.
- `aliases` carries the translation or transliteration, so search finds it
  either way.
- `language` is set only when the body isn't English.
- Books in another language get a two-paragraph summary: English first, then the
  original language.

---

## Where the files live

```
<your-vault>/
  *.md                              your notes
  meta/
    ontology.yaml                   canonical types      ← replaced on upgrade
    ontology-user.yaml              your types           ← yours, kept forever
    relation-dictionary.yaml        canonical relations  ← replaced on upgrade
    relation-dictionary-user.yaml   your relations       ← yours, kept forever
    scheme-dictionary.yaml          canonical schemes    ← replaced on upgrade
    scheme-dictionary-user.yaml     your schemes         ← yours, kept forever
    tag-dictionary.md               your tag vocabulary  ← yours to grow
    type-dictionary.md              plain-English type guide
    field-dictionary.md             field-by-field reference
    foreign-definitions.md          schemas for external sources (Jira, etc.)
    ontology-guide.md               this document        ← replaced on upgrade
```

Files marked "replaced on upgrade" are refreshed automatically when Loci's meta
version advances — you'll see a one-line notice next time you save. Everything
marked "yours" survives untouched. **Don't edit the canonical files**: your
changes will vanish on the next upgrade, and the user files exist precisely so
you don't have to.

---

## Asking Claude about it

You don't have to read YAML. Any of these work:

- *"What fields does an `event` need?"*
- *"Show me the relation types for provenance."*
- *"Which schemes can I use for a file in Dropbox?"*
- *"Lint my vault and tell me what's broken."*
- *"Define a `workout` type extending `procedure`."*

Claude reads the same registry files the system enforces, so the answer is
always the live truth rather than a description of it.

---

## See also

These live in the [Loci repository](https://github.com/gked/loci), not in your
vault:

- [`docs/file-saving.md`](https://github.com/gked/loci/blob/main/docs/file-saving.md)
  — how a file on disk becomes a note
- [`docs/execution-flows.md`](https://github.com/gked/loci/blob/main/docs/execution-flows.md)
  — what happens on each tool call
- [`src/loci/skills/references/ontology-system.md`](https://github.com/gked/loci/blob/main/src/loci/skills/references/ontology-system.md)
  — the developer guide to the enforcement machinery
