# The Problem

Why Loci exists, and why a folder of Markdown or a PKM app on its own doesn't cover it. For what Loci *is*, see the [README](../README.md).

---

**Knowledge and content are fragmented across apps, devices, cloud accounts, and formats. There is no unified place where intellectual output (things read, produced, saved, researched, or thought) is captured, organized, and retrievable.**

Notes in one app, articles in a read-later queue, bookmarks in the browser, decisions buried in chat logs, ebooks in a folder, PDFs on a cloud drive, tasks somewhere else. Each tool owns its own schema and none of them link to each other. The connection between the book you read in March, the note you wrote about it in June, and the project it changed in September exists only in your head, and only until you forget it.

That shows up as six distinct failures:

**Ingestion.** No reliable way to capture content from arbitrary apps, devices, or contexts into a single store.

**Organization.** No consistent structure for tagging, categorizing, or linking related content. "AI", "ai", and "machine-learning" become three different tags; nothing stops the fourth.

**Retrieval.** No way to query across everything you've saved. Search matches strings, so it finds the note you already remembered, not the one you forgot.

**Reflection.** No way to see how your thinking on a topic has changed. You can find what you believe now, but not what you believed two years ago or what changed your mind.

**LLM accessibility.** Saved knowledge is not structured in a way that an LLM can reason over. An agent dropped into an unstructured folder re-derives the schema on every question, guesses what fields mean, and invents its own vocabulary on write, so the vault drifts a little further from itself each session.

**Memory.** There is no concept of a human digital memory that sits independently outside AI systems. Everything you tell an assistant lives in that assistant's store, on that vendor's terms.

### Why the obvious answers fall short

**A folder of Markdown** fixes lock-in and nothing else. Without stable identifiers, renaming a file breaks every reference to it. Without a declared vocabulary, tags drift. Without typed edges, "related to" means everything and therefore nothing. The result is searchable but not navigable.

**A database or a PKM app** fixes the structure and takes back the ownership: proprietary storage, no `grep`, no `git log`, no editing a file in your own text editor, and an export button you'll never have to trust until the day you do.

Loci's position is that you shouldn't have to choose. The Markdown file is always the source of truth. The graph is a query engine built on top of it, not a second store that can disagree with it.

### Doing the ontology on purpose

The moment you decide what a tag means, which relationships exist, and what makes two notes "related" rather than one being "part of" the other, you are doing ontology. The only real choice is whether you do it consciously or by accident.

| Formality | Approach | Where |
|---|---|---|
| Lightweight | Tags and a handful of link types | Obsidian, Roam |
| **Mid-weight** | **Typed nodes with defined fields, typed edges with defined semantics** | **Loci** |
| Heavy | Full OWL/RDF with an inference engine | Academic knowledge graphs |

Loci sits in the middle on purpose: enough structure for an LLM to reason over the graph, not so much that maintaining it becomes the hobby. Types, fields, relations, and storage schemes are declared in versioned YAML registries that both you and your agents are held to, validated on write and linted after.

### What that buys you

| Failure mode | Loci's answer |
|---|---|
| Scattered across silos | One vault. Notes, articles, tasks, books, people, and conversations are all nodes in the same graph. |
| Renaming breaks references | Every node has a stable 8-character UID. Links point at UIDs, never filenames. |
| "Related to" means nothing | A registry of 27 typed relations, plus their named inverses (`depends-on`, `contradicts`, `supersedes`, …). Unknown relations are rejected on write. |
| Vocabulary drift | Types, fields, relations, and location schemes live in versioned registries. `lint_vault` catches whatever slips through. |
| Files scattered across drives | A node records *where* a file is (`local`, `google-drive`, `nextcloud`, `url`, `gmail`, `s3`, …) instead of forcing you to copy everything into one place. |
| Agents that guess | Loci ships as an MCP server with skills. Claude reads the ontology before writing, so it uses your vocabulary rather than inventing one. |
| Thinking that leaves no trace | `supersedes`, `version-of`, and `is-based-on` edges, plus `log` nodes, record how a position changed rather than silently overwriting it. |
| Lock-in | Markdown in a directory you chose. Delete Loci tomorrow and the vault still opens in any editor. |

A vault is only as smart as its edges. Content without relationships is just storage, so edges get recorded at capture time by an agent that suggests links and asks you to confirm them, rather than left as a cleanup task you never get to. What that opens up is questions you couldn't ask a folder: *what do I know about stoicism?* returns the books, the reading logs, the notes, the people, and the paths between them.
