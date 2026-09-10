# Examples

One prompt per situation, what Loci writes, and how you get it back. Every
example assumes you have told Claude once to treat "save", "remember", and
"what do I know" as vault operations — see
[Teach the agent once](usage.md#teach-the-agent-once). Until then, say "loci"
or "my vault" in the request.

Each save ends the same way: Claude proposes a type, suggests links to nodes
you already have, and asks you to confirm before writing. Say "just save it"
if you want fewer questions.

---

## Storing

### A bookmark — a URL, nothing extracted

```
Bookmark this: https://example.com/tools/some-cli
```

→ `bookmark` node with `source_url` and `site_name`. No content is fetched.

### An article — something with a source, read now or later

```
Save this article: https://example.com/essay-on-attention
Save this article, and note that it argues against the piece I saved last week on the same topic
```

→ `article` node with `source_url`, `author`, `published_at`, a summary, and a
format tag (`#blog-post`, `#research-paper`, …). The second form adds a
`contradicts` edge to the earlier node.

### A document — your own text, no citable source

```
Save this as a document: <paste, or "the file I have open">
Save my notes from today's design review as meeting notes
```

→ `document` node with `status` and a format tag (`#meeting-notes`, `#essay`,
`#spec`, …). If it reads as a sequence of steps, Claude will suggest
`procedure` instead.

### A reference to a file you keep elsewhere

```
Reference this in my vault, don't copy it: ~/Documents/contracts/lease-2026.pdf
Save a reference to the Q3 plan in Google Drive: <link>
```

→ a node of whatever type the content is (`document`, `article`, `asset`) with
a `has_asset` entry recording *where* the file is — `scheme: local` with the
path, `scheme: google-drive` with the file id, and so on. The file stays put.
To have Loci own the copy instead, drop it in `loci-stage/` and run the inbox
(below).

### A book you own — on the shelf or as an ebook

```
Add this book to my library: Thinking, Fast and Slow, Kahneman, paperback on my shelf
Add this ebook to my library: ~/Books/name-of-the-rose.epub
```

→ `asset` node with `subtype: book` and `storage: physical | digital | both`;
the ebook form also gets a `has_asset` location. A book you *read* but don't
own is an `article` with `format: book` instead — Claude will ask if it can't
tell.

### Reading notes on a book

```
Log a reading: I started The Name of the Rose today
Log a reading: finished The Name of the Rose, 5/5. Highlights: <paste>
```

→ one `log` node per reading, tagged `reading`, with `subject_uid` pointing at
the book, `log_status`, `started_at` / `finished_at`, `rating`, and
`highlights`. Re-reading the book later makes a second `log`, so the two
readings — and how your opinion moved — stay separate.

### A task

```
Add a task: renew the lease before 30 September, high priority
```

→ `task` node with `status`, `due_date`, `priority`, linked to the lease
document if one exists.

### A project

```
Start a project: rebuild the garden shed. Goals: weatherproof by October, under $2k
```

→ `project` node with `status`, `goals`, `milestones`, `due_date`. Later tasks
and notes get a `belongs-to` edge to it when you mention the shed.

### An event

```
Save an event: dentist, 14 October 10:00, Dr Okafor's clinic
```

→ `event` node with `start_at`, `end_at`, `location`, `participants`.

### A person, organisation, or place

```
Save an entity: Dana Okafor, dentist at Riverside Clinic
Save an entity: Riverside Clinic, dental practice on Main Street
```

→ `entity` nodes with `subtype: person | organization | place` and the
relevant fields (`roles`, `organization`, `website`, …). Entities are what
`mentions` edges point at, so saving the people and organisations you deal
with is what makes "what do I know about X" answer with paths.

### A procedure — steps with an outcome

```
Save this recipe: <paste>
Save how I set up a new machine as a playbook: <steps>
```

→ `procedure` node with `steps`, `expected_outcome`, `inputs`,
`duration_minutes`, and a format tag (`#recipe`, `#playbook`, `#protocol`, …).

### A conversation

```
Save this conversation to my vault
Save the thread with the contractor from email as a conversation
```

→ `conversation` node with `participants`, `platform`, `model` (for an LLM
chat), `turns`. From email, `has_asset` points at the thread with the `gmail`
scheme rather than copying it.

### A topic — a hub with no content of its own

```
Create a topic: stoicism. Link the Marcus Aurelius notes and the two reading logs to it
```

→ `topic` node with `status`; the named nodes get edges to it. If you would
only ever use the subject as a filter, a tag is better — Claude will say so.

### A backlog of files

```
Process my inbox
```

→ scans `loci-stage/`, shows a plan with counts and estimates, and on approval
ingests in resumable batches. To register a folder in place without moving
anything: `Ingest ~/Documents/papers into my vault`.

---

## Retrieving

```
What do I know about stoicism?
What's connected to the shed project?
What did I save in the last two weeks?
How is the lease document related to Dana Okafor?
Show me all open tasks
Show me the reading logs I finished this year
What did I think of The Name of the Rose the first time I read it?
```

Answers come from the graph — types, tags, statuses, dates, and edges — not
from text search, so "open tasks" is a status filter and the last one walks
from the book to its earliest `log`. Plain search is there too:
`Search my vault for "attention"`.

---

## Updating

```
Mark the lease task done
Add a note to the shed project: contractor quote came in at $1,800
Archive the Q3 plan document
Actually the attention essay supersedes the one from last week, not contradicts — fix the link
```

→ patches to the existing node. Edits are permissive (you are not blocked by
rules about fields you aren't touching); archiving sets `state: archived` and
hides the node from default queries without deleting it.

---

## Extending the ontology

```
Define a `recipe` type that extends `procedure`, with optional `servings` and `cuisine` fields
Define a `cooked-from` relation, inverse of `is-based-on`, for a log that records making a recipe
Save this recipe as a recipe: <paste>. Servings 4, Italian
Log a cooking: made the carbonara tonight, 4/5, cooked-from the recipe
What have I cooked from that recipe?
```

The first two append to `ontology-user.yaml` and
`relation-dictionary-user.yaml` and are live immediately; the rest use them
like any shipped type. The rules and how the user layer sits on the canonical
one are in [usage.md](usage.md#extending-the-ontology).
