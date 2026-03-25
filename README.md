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

## Setup — Docker (recommended)

The easiest way to run Loci. Docker handles dependencies and sync inside the container.

### 1. Clone the repo

```bash
git clone https://github.com/you/loci.git
cd loci
```

### 2. Run the setup script

```bash
python setup_docker.py
```

The script will:
- Check for Docker or OrbStack — and offer to install one via Homebrew if neither is found
- Ask where the vault should live
- Optionally configure rclone sync (Nextcloud, Dropbox, Google Drive, S3, and more)
- Build the image and start the container
- Verify the server is responding

### 3. Restart Claude Code

The setup script installs the skill automatically. Restart Claude Code to pick it up.

### 4. Test it

Open Claude Code and say:

```
Save this as a note: Loci is now set up and working.
```

### How Docker and the vault interact

The vault is **not inside the container**. Docker runs the MCP server process and the rclone sync loop — your vault data lives on the host filesystem and is mounted into the container at `/vault` at runtime. This means:

- Vault data persists across container restarts and rebuilds
- You can stop, update, or replace the container without touching your notes
- The same vault can be used by the local stdio server (Claude Code / Claude Desktop) and the Docker SSE server simultaneously

Your rclone config is mounted in read-only from the host — credentials are never baked into the image.

### Managing the container

**Terminal:**

```bash
# Restart (no rebuild)
docker compose -f deploy/docker-compose.yml restart

# Rebuild after code changes
VAULT_PATH=/absolute/path/to/vault docker compose -f deploy/docker-compose.yml up -d --build

# Stop
docker compose -f deploy/docker-compose.yml down

# View logs
docker compose -f deploy/docker-compose.yml logs -f
```

**OrbStack:**

Open the OrbStack app — the `loci` container will appear in the sidebar. From there you can restart, stop, or view logs with a single click without needing the terminal.

---

## Setup — Local (Python)

Run the MCP server directly on your machine without Docker. Use this if you want to run Loci locally with Claude Code or Claude Desktop only.

**Requires:** Python 3.13+, [uv](https://docs.astral.sh/uv/), [rclone](https://rclone.org/)

### 1. Clone the repo

```bash
git clone https://github.com/you/loci.git
cd loci
```

### 2. Initialize

```bash
python setup.py
```

This will:
- Install dependencies via uv
- Ask where the vault should live (default: `vault/` inside the project)
- Ask which rclone remote to use for sync
- Create the vault folder structure and seed meta dictionaries
- Register the MCP server with Claude Code and Claude Desktop

### 3. Configure sync

```bash
cp sync/rclone.conf.sample ~/.config/rclone/rclone.conf
# edit with your credentials
```

Pull the vault from the remote on first setup:

```bash
./sync/sync.sh pull
```

To sync automatically on vault changes, install the watcher for your platform:

- **macOS:** `cp sync/com.loci.sync.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.loci.sync.plist`
- **Linux:** copy `sync/loci-sync.path` and `sync/loci-sync.service` to `/etc/systemd/system/` and run `systemctl enable --now loci-sync.path`

### 4. Install the Loci skill in Claude Code

```bash
cp -r loci-skill/loci-save/ ~/.claude/skills/loci-save/
```

### 5. Test it

Open Claude Code and say:

```
Save this as a note: Loci is now set up and working.
```

---

## Remote Access (Claude.ai / mobile)

To use Loci from Claude.ai or mobile, the MCP server needs to be reachable via HTTPS.

Put the container behind nginx and Cloudflare Access:

1. Copy and fill in the nginx config: `deploy/nginx.conf.sample` → `/etc/nginx/sites-available/loci`
2. Set up [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/) to protect the endpoint
3. Add the HTTPS endpoint in Claude.ai → Settings → Integrations

See `deploy/nginx.conf.sample` for the full nginx config.

---

## Usage

Just describe what you want to save:

```
Save this as a note: ...
Add this article: https://example.com/article
Create a task: Review the Loci architecture by Friday
Save this entity: John Smith, CEO at Acme Corp
```

Claude will classify the type, generate frontmatter, suggest entity links, and write the file.

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
    Dockerfile
    docker-compose.yml
    entrypoint.sh                 ← pulls vault on startup, runs background sync
    loci-mcp.service              ← systemd service for always-on SSE server
    nginx.conf.sample             ← nginx config for SSE + Cloudflare
  api.py
  setup.py
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
- [x] Docker image — containerize MCP server with vault as a mounted volume

### Next
- [ ] Graph layer — NetworkX in-memory for bootstrap phase; migrate to Kuzu once vault reaches meaningful size or traversal performance matters
- [ ] Loci query skill — retrieve, relate, summarize across vault nodes
- [ ] Testing suite — vault_init correctness, schema validation, duplicate detection, ingestion edge cases
- [ ] Cloudflare Access setup guide

### Later
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

---

## Contributing

Coming soon.
