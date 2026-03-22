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

- Python 3.10+
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
pip install -r requirements.txt
```

### 3. Initialize the vault

```bash
python tools/vault_init.py
```

This will:
- Ask where your Nextcloud folder is on this machine
- Ask what to call the vault folder (default: `loci`)
- Create the full folder structure inside Nextcloud
- Save your config to `~/.loci/config.yml`
- Seed the vault with `meta/type-dictionary.md` and `meta/foreign-definitions.md`

### 4. Install the Loci skill in Claude Code

Copy or symlink the skill into your Claude Code skills directory:

```bash
cp -r skill/ ~/.claude/skills/loci-save/
```

Or install the `.skill` file if packaged.

### 5. Test it

Open Claude Code and say:

```
Save this as a note: Loci is now set up and working.
```

Claude should create a file at:
```
~/Nextcloud/loci/notes/YYYY-MM-DD-loci-is-now-set-up-and-working.md
```

---

## Project Structure

```
loci/
  skill/
    SKILL.md                    ← Claude's instructions for saving content
    references/
      type-fields.md            ← type-specific frontmatter fields
  tools/
    uid_generator.py            ← generates stable 8-char hex UIDs
    slug.py                     ← converts titles to filename slugs
    vault_init.py               ← first-run setup and vault scaffolding
    write_file.py               ← writes vault items to the filesystem
  loci_mcp/
    server.py                   ← MCP server (Claude Desktop, stdio transport)
    tools/
      write_vault.py            ← WebDAV write tool (placeholder — TBD)
      read_vault.py             ← WebDAV read tool (placeholder — TBD)
  requirements.txt
  README.md
```

---

## Vault Structure

```
~/Nextcloud/loci/
  /notes/
  /articles/
  /conversations/
  /projects/
  /tasks/
  /events/
  /entities/
  /procedures/
  /topics/
  /references/
  /meta/
    config.yml                  ← vault config (path, webdav url)
    type-dictionary.md          ← canonical type vocabulary
    foreign-definitions.md      ← external source schemas
```

---

## Configuration

Config lives at `~/.loci/config.yml` — separate from the repo so it is never committed to git.

```yaml
vault_root: ~/Nextcloud/loci
webdav_url: null               # TBD when Claude.ai MCP layer is built
created_at: 2026-03-21T14:32:00Z
version: 1
```

To reconfigure (e.g. on a new machine):

```bash
python tools/vault_init.py --force
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

- [x] Core vault structure and schema
- [x] Claude Code save skill
- [x] vault_init, uid_generator, slug, write_file tools
- [ ] SQLite graph indexer
- [ ] Vector DB integration (ChromaDB or LanceDB)
- [ ] Claude.ai MCP server (WebDAV)
- [ ] Telegram bot (bidirectional ambient interface)
- [ ] Browser extension / bookmarklet
- [ ] Loci query skill (retrieve, relate, summarize)

---

## Design Decisions

Key decisions are documented in `loci-requirements.md`. If you are contributing or extending Loci, read that first.
