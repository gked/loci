# Loci

Your personal knowledge vault. Capture, organize, and retrieve everything you think about, read, and produce — structured for both human navigation and LLM reasoning.

---

## What is Loci?

Loci is a personal knowledge management system built on plain Markdown files with YAML frontmatter, stored in Nextcloud and organized as a traversable knowledge graph. It is designed to be accessed by both you and LLM agents (Claude Code, Claude.ai).

Every piece of content you save becomes a structured node with:
- A stable UID
- Typed relationships to other nodes
- Semantic metadata (tags, domains, summary)
- A place in a consistent folder structure

---

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Nextcloud (self-hosted or cloud) with the desktop client syncing to a local folder
- Claude Code (for local use) or Claude.ai with the Loci skill installed

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/you/loci.git
cd loci
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Initialize the vault

```bash
python setup.py
```

This will:
- Ask where your Nextcloud folder is on this machine
- Ask what to call the vault folder (default: `loci`)
- Create the full folder structure inside Nextcloud
- Save your config to `config.yml` in the project root
- Seed the vault with all meta dictionaries
- Register the MCP server with Claude Desktop

### 4. Install the Loci skill in Claude Code

Copy or symlink the skill into your Claude Code skills directory:

```bash
cp -r loci-skill/loci-save/ ~/.claude/skills/loci-save/
```

### 5. Test it

Open Claude Code and say:

```
Save this as a note: Loci is now set up and working.
```

Claude should create a file at:
```
~/Nextcloud/loci/notes/loci-is-now-set-up-and-working.md
```

---

## Project Structure

```
loci/
  loci-skill/
    loci-save/
      SKILL.md                  ← Claude's instructions for saving content
    references/
      type-fields.md            ← legacy type fields reference (superseded by field-dictionary)
  loci_mcp/
    server.py                   ← MCP server (Claude Desktop, stdio transport)
  tools/
    uid_generator.py            ← generates stable 8-char hex UIDs
    slug.py                     ← converts titles to filename slugs
    vault_init.py               ← first-run setup and vault scaffolding
    write_file.py               ← writes vault items to the filesystem
  api.py                        ← core vault API (read, write, patch, delete, list, duplicate check)
  setup.py                      ← interactive setup: config, vault init, MCP registration
  run_server.sh                 ← starts the MCP server
  config.yml                    ← local config (not committed — see config.sample.yml)
  pyproject.toml                ← project metadata and dependencies
  uv.lock                       ← locked dependency versions
  README.md
```

---

## Vault Structure

```
~/Nextcloud/loci/
  /notes/
  /articles/
  /bookmarks/
  /conversations/
  /projects/
  /tasks/
  /events/
  /entities/
  /procedures/
  /topics/
  /references/
  /meta/
    type-dictionary.md          ← canonical type vocabulary
    tag-dictionary.md           ← freeform tag vocabulary
    field-dictionary.md         ← field definitions per type (authoritative schema)
    foreign-definitions.md      ← external source schemas (Jira, calendar, etc.)
```

---

## Configuration

Config lives at `config.yml` in the project root — gitignored, never committed. See `config.sample.yml` for the template.

```yaml
vault_root: ~/Nextcloud/loci
webdav_url: null               # TBD when Claude.ai MCP layer is built
created_at: 2026-03-21T14:32:00Z
version: 1
```

To reconfigure (e.g. on a new machine):

```bash
python setup.py
```

---

## Usage

### Saving content via Claude Code

Just describe what you want to save:

```
Save this as a note: ...
Add this article: https://example.com/article
Create a task: Review the Loci architecture by Friday
Save this entity: John Smith, CEO at Acme Corp
```

Claude will:
1. Classify the type
2. Generate frontmatter
3. Suggest entity links
4. Write the file to the correct vault folder

### Saving content via Claude.ai

Same natural language — but requires the MCP layer to be set up first (see `loci_mcp/` folder). Until then, use Claude Code.

---

## Roadmap

### Done
- [x] Core vault structure and schema
- [x] Claude Code save skill (loci-save)
- [x] vault_init, uid_generator, slug, write_file tools
- [x] MCP server — local stdio transport, Claude Desktop integration
- [x] patch and delete operations
- [x] Field dictionary — authoritative schema in vault meta, skill reads at runtime

### Next
- [ ] Graph layer — NetworkX in-memory for bootstrap phase; migrate to Kuzu once vault reaches meaningful size or traversal performance matters. SQLite considered and rejected: relational model creates unnecessary friction for multi-hop graph queries
- [ ] Loci query skill — retrieve, relate, summarize across vault nodes
- [ ] Testing suite — vault_init correctness, schema validation, graph indexing, skill classification and duplicate detection, ingestion edge cases

### Later
- [ ] Vector DB — deferred; at personal vault scale, pass summaries to the LLM for semantic retrieval. No embeddings needed until summaries exceed context window. Revisit ChromaDB / LanceDB / Qdrant at that point
- [ ] Claude.ai MCP server (WebDAV transport)
- [ ] Browser extension / bookmarklet
- [ ] Mobile capture — iOS Share Sheet
- [ ] Telegram bot — bidirectional ambient interface (inbound save + outbound reminders and suggestions)

### Open questions
- Relationship inference: at what vault size does automatic inference become useful vs. noisy?
- Decay heuristics: what signals indicate a note is going stale?
- Journal privacy: separate encryption layer for private entries?
- Content editing model: edit in place, or new node linked via `supersedes` / `revisits`?
- History tracking: implicit (git log) or explicit (encoded in graph)?
- `reference` type placement: currently Structural, may belong under Content — revisit

---

## Design Decisions

Key decisions are documented in the Loci vault at `notes/2026-03-21-locus-requirements.md`. If you are contributing or extending Loci, read that first.
