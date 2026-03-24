# Loci

Your personal knowledge vault. Capture, organize, and retrieve everything you think about, read, and produce — structured for both human navigation and LLM reasoning.

---

## What is Loci?

Loci is a personal knowledge management system built on plain Markdown files with YAML frontmatter, organized as a traversable knowledge graph. It is designed to be accessed by both you and LLM agents (Claude Code, Claude.ai).

Every piece of content you save becomes a structured node with:
- A stable UID
- Typed relationships to other nodes
- Semantic metadata (tags, domains, summary)
- A place in a consistent folder structure

---

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [rclone](https://rclone.org/) (for vault sync)
- Claude Code (for local use) or Claude.ai (remote, requires deployment)

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
- Ask where the vault should live (default: `vault/` inside the project)
- Ask which rclone remote to use for sync
- Create the full folder structure
- Save your config to `config.yml` in the project root
- Seed the vault with all meta dictionaries
- Register the MCP server with Claude Desktop

### 4. Configure sync

Copy and fill in the rclone config template:

```bash
cp sync/rclone.conf.sample ~/.config/rclone/rclone.conf
# edit with your credentials
```

Pull the vault from the remote (on first setup or new machine):

```bash
./sync/sync.sh pull
```

Push local changes:

```bash
./sync/sync.sh push
```

To sync automatically on vault changes, install the watcher for your platform:

- **macOS:** `cp sync/com.loci.sync.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.loci.sync.plist`
- **Linux:** copy `sync/loci-sync.path` and `sync/loci-sync.service` to `/etc/systemd/system/` and run `systemctl enable --now loci-sync.path`

### 5. Install the Loci skill in Claude Code

```bash
cp -r loci-skill/loci-save/ ~/.claude/skills/loci-save/
```

### 6. Test it

Open Claude Code and say:

```
Save this as a note: Loci is now set up and working.
```

---

## Project Structure

```
loci/
  vault/                          ← vault lives here (gitignored, synced via rclone)
  loci-skill/
    loci-save/
      SKILL.md                    ← Claude's instructions for saving content
  loci_mcp/
    server.py                     ← MCP server (stdio or SSE via LOCI_TRANSPORT)
  tools/
    uid_generator.py
    slug.py
    vault_init.py
    write_file.py
  sync/
    rclone.conf.sample            ← rclone remote config template
    sync.sh                       ← push/pull/bisync wrapper
    loci-sync.path                ← systemd path watcher (Linux)
    loci-sync.service             ← systemd sync service (Linux)
    com.loci.sync.plist           ← launchd watcher (macOS)
  deploy/
    loci-mcp.service              ← systemd service for always-on SSE server
    nginx.conf.sample             ← nginx config for SSE + Cloudflare
  api.py
  setup.py
  run_server.sh
  config.yml                      ← local config (gitignored — see config.sample.yml)
  pyproject.toml
  uv.lock
  README.md
```

---

## Vault Structure

```
vault/
  notes/
  articles/
  bookmarks/
  conversations/
  projects/
  tasks/
  events/
  entities/
  procedures/
  topics/
  references/
  meta/
    type-dictionary.md            ← canonical type vocabulary
    tag-dictionary.md             ← freeform tag vocabulary
    field-dictionary.md           ← field definitions per type
    foreign-definitions.md        ← external source schemas (Jira, calendar, etc.)
```

---

## Configuration

Config lives at `config.yml` in the project root — gitignored, never committed. See `config.sample.yml` for the template.

```yaml
vault_root: /path/to/loci/vault   # default: <project_root>/vault
sync_remote: nextcloud             # rclone remote name
sync_remote_path: loci             # path on the remote
```

To reconfigure (e.g. on a new machine):

```bash
python setup.py
```

---

## Sync

Loci uses [rclone](https://rclone.org/) for vault sync. rclone supports Nextcloud, Dropbox, Google Drive, OneDrive, S3, and ~50 other providers. Swapping providers is a config change — no code changes needed.

The vault is local on every machine that runs the MCP server. Sync keeps all machines in agreement.

---

## Remote Deployment (Claude.ai / mobile)

To use Loci from Claude.ai on mobile, deploy the MCP server on a server reachable via HTTPS.

### Option A — Docker (recommended)

```bash
# Build and start
VAULT_PATH=/absolute/path/to/vault docker compose -f deploy/docker-compose.yml up -d
```

The container mounts your vault at `/vault` and runs the MCP server in SSE mode on port 8000. `VAULT_PATH` defaults to `../vault` relative to the project root if not set.

Then put nginx + Cloudflare Access in front (see `deploy/nginx.conf.sample`) and add the endpoint in Claude.ai → Settings → Integrations.

### Option B — systemd

1. Clone the repo and pull the vault on the server
2. Set `LOCI_TRANSPORT=sse` in the environment (or systemd unit)
3. Use `deploy/loci-mcp.service` for the systemd service
4. Use `deploy/nginx.conf.sample` for the nginx config
5. Put Cloudflare Access in front for auth
6. Add the endpoint in Claude.ai → Settings → Integrations

See `deploy/` for config templates.

---

## Usage

### Saving content

Just describe what you want to save:

```
Save this as a note: ...
Add this article: https://example.com/article
Create a task: Review the Loci architecture by Friday
Save this entity: John Smith, CEO at Acme Corp
```

Claude will classify the type, generate frontmatter, suggest entity links, and write the file.

---

## Roadmap

### Done
- [x] Core vault structure and schema
- [x] Claude Code save skill (loci-save)
- [x] vault_init, uid_generator, slug, write_file tools
- [x] MCP server — local stdio transport, Claude Desktop integration
- [x] patch and delete operations
- [x] Field dictionary — authoritative schema in vault meta, skill reads at runtime
- [x] rclone sync layer — provider-agnostic vault sync
- [x] SSE transport — remote MCP server support (Claude.ai / mobile)
- [x] deploy/ — systemd + nginx templates for server deployment

### Next
- [ ] Graph layer — NetworkX in-memory for bootstrap phase; migrate to Kuzu once vault reaches meaningful size or traversal performance matters
- [ ] Loci query skill — retrieve, relate, summarize across vault nodes
- [ ] Testing suite — vault_init correctness, schema validation, duplicate detection, ingestion edge cases
- [ ] Cloudflare Access setup guide

### Later
- [x] Docker image — containerize MCP server with vault as a mounted volume; simplifies lab server deployment and distribution
- [ ] Vector DB — deferred until summaries exceed context window. Revisit ChromaDB / LanceDB / Qdrant at that point
- [ ] Browser extension / bookmarklet
- [ ] Native mobile / desktop apps (local-first, SQLite backend — see planning doc)
- [ ] Telegram bot — bidirectional ambient interface

### Open questions
- Relationship inference: at what vault size does automatic inference become useful vs. noisy?
- Decay heuristics: what signals indicate a note is going stale?
- Journal privacy: separate encryption layer for private entries?
- Content editing model: edit in place, or new node linked via `supersedes` / `revisits`?
- History tracking: implicit (git log) or explicit (encoded in graph)?

---

## Design Decisions

Key decisions are documented in the Loci vault at `notes/2026-03-21-locus-requirements.md`. If you are contributing or extending Loci, read that first.
