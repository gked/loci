# Loci

Your personal knowledge vault. Capture, organize, and retrieve everything you think about, read, and produce — structured for both human navigation and LLM reasoning.

---

## The Name

*Loci* is the Latin plural of *locus* — "places" or "locations."

The most relevant origin is the **method of loci**, an ancient mnemonic technique dating back to classical antiquity. To use it, you mentally place pieces of information at specific locations along a familiar route or building — a memory palace — then walk through it to retrieve them. It's one of the oldest and most effective memory systems ever described.

The word carries the same spatial meaning across other domains: in mathematics, a *locus* is the set of all points satisfying a condition; in genetics, a *locus* is a fixed position on a chromosome where a gene lives; in Latin phrases like *locus classicus* (the authoritative passage on a topic), the root always points to a specific, defined place.

That's the idea behind this project. Every note, article, task, and conversation you save gets a **fixed location** in a structured graph — a stable UID, typed relationships, semantic metadata. You (and your LLM agents) can navigate it the way a memory palace is navigated: by association, by position, by path.

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
uv run setup_docker.py
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

The vault is **not inside the container**. Docker runs the MCP server process and the rclone sync loop — your vault data lives on the host filesystem and is mounted into the container at `/knowledge-vault` at runtime. This means:

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
VAULT_PATH=/absolute/path/to/knowledge-vault docker compose -f deploy/docker-compose.yml up -d --build

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


### 4. Install the Loci skill in Claude Code

```bash
cp -r loci-skill/loci-save/ ~/.claude/skills/loci-save/
```

### 5. Restart the MCP server

After code changes, restart the server by running:

```bash
uv run --directory /path/to/loci python loci_mcp/server.py
```

For Claude Desktop, the server is managed by the app — just quit and reopen Claude Desktop. For Claude Code, restart the session or toggle the MCP connection in settings.

### 6. Test it

Open Claude Code and say:

```
Save this as a note: Loci is now set up and working.
```

---

## Remote Access (Claude.ai / mobile)

To use Loci from Claude.ai, Claude Desktop, or mobile, run the MCP server on a Linux home lab server and expose it via Cloudflare Tunnel — no open ports, no domain required.

```bash
bash deploy/setup-homelab.sh
```

The script installs Docker, rclone, and cloudflared; creates a named tunnel; and starts the container. Once running:

- **Claude Desktop / Claude Code:** `claude mcp add --transport sse loci <tunnel-url>/sse --scope user`
- **Claude.ai / mobile:** Settings → Connectors → Add custom connector → `<tunnel-url>/sse`

The vault lives on the server and is the single source of truth. All clients connect to the same endpoint. Nextcloud backup runs daily if `BACKUP_REMOTE` is configured in `deploy/.env`.

**Authentication:** after setup, protect the tunnel with [Cloudflare Zero Trust Access](https://one.dash.cloudflare.com) — Access → Applications → Add Self-hosted app → policy: your email. Without this the endpoint is open.

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
  knowledge-vault/                ← vault lives here (gitignored, synced via rclone)
  loci-skill/
    loci-save/
      SKILL.md                    ← Claude's instructions for saving content
    loci-query/
      SKILL.md                    ← Claude's instructions for querying content
    references/
      type-dictionary.md          ← seed: canonical type vocabulary
      field-dictionary.md         ← seed: field definitions per type
      tag-dictionary.md           ← seed: initial tag vocabulary
      relation-dictionary.md      ← seed: typed edge vocabulary
      foreign-definitions.md      ← seed: external source schemas
      type-fields.md              ← human-readable field reference by type
  loci_mcp/
    server.py                     ← MCP server (stdio or SSE via LOCI_TRANSPORT)
                                    env vars: LOCI_TRANSPORT=stdio|sse
                                              LOCI_VAULT_ROOT=/path/to/knowledge-vault
                                              LOCI_PORT=8000 (SSE only, default 8000)
                                              LOCI_TOKEN=<secret> (SSE only, optional bearer auth)
  tools/
    uid_generator.py
    slug.py
    vault_init.py
    write_file.py
    asset_registry.py              ← asset resolve, register, find-unregistered, crash recovery
  sync/
    rclone.conf.sample            ← rclone remote config template
    sync.sh                       ← push/pull/bisync wrapper

  deploy/
    Dockerfile
    docker-compose.yml
    entrypoint.sh                 ← starts MCP server; optional daily backup to Nextcloud
    setup-homelab.sh              ← one-shot setup script for Linux home lab server
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
~/Nextcloud/loci/                    ← loci root (all stores are siblings)
  knowledge-vault/                   ← knowledge graph — markdown only
    documents/
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
      type-dictionary.md        ← canonical type vocabulary       (schema_version: N)
      field-dictionary.md       ← field definitions per type      (schema_version: N)
      tag-dictionary.md         ← freeform tag vocabulary         (schema_version: N)
      relation-dictionary.md    ← typed edge vocabulary           (schema_version: N)
      foreign-definitions.md    ← external source schemas         (schema_version: N)

  assets/                       ← binary/rich files (HTML, PDF, PNG, etc.)
    <uid>.<ext>                 ← one file per asset, named by vault node UID

  asset-registry/               ← resolver layer — decouples vault from file locations
    <uid>.yaml                  ← one registry entry per asset (format, mime, locations)
    manifest.txt                ← flat list of all registered asset paths (one per line)
    .pending/                   ← intent files for crash recovery during writes
```

Vault nodes reference assets by setting `has_asset: true`. The registry maps UIDs to physical
file locations. If a file moves, only the registry entry changes — vault nodes are untouched.

---

## Schema Versioning

Each vault meta file carries a `# schema_version: N` comment. The project-side seed files live in `loci-skill/references/` and are the source of truth for what a fresh vault gets. `vault_init.py` reads from these files to seed the vault on first run.

`config.yml` tracks `meta_version: N` — the version of the schema that was used to seed this vault. Future upgrade scripts compare this against the current `META_VERSION` in `vault_init.py` to determine what migrations to apply.

### Adding a new type or field (non-breaking)

1. Edit the relevant file in `loci-skill/references/`
2. Increment `schema_version` in that file and `META_VERSION` in `vault_init.py`
3. Apply the same change to the live vault meta file (your `vault/meta/`)
4. Update `meta_version` in `config.yml`

### Breaking changes (rename, remove, restructure)

Breaking changes require an explicit migration script (`tools/migrate_v1_to_v2.py`) that reads the live vault, transforms affected nodes, and updates `meta_version` in `config.yml`. Document the change in a changelog entry.

### Why two copies?

The vault meta files are user-owned — they accumulate customizations (new tags, local schema tweaks) that the project seeds don't have. The `loci-skill/references/` files are the initial template only. Non-breaking additions can be auto-applied by a future `vault_upgrade.py`; breaking changes always require explicit migration.

---

## Vault Topology Visualization

`viz_vault.py` renders a graph of all vault nodes and their relationships as a PNG.

```bash
uv run python viz_vault.py
```

Output is saved to `/tmp/loci_topology.png`. Open it with:

```bash
open /tmp/loci_topology.png
```

**What it shows:**
- Each node is a vault item, colored by type (see legend)
- Edges are typed relations (e.g. `belongs-to`, `parent-of`, `about`)
- Arrows show direction (source → target)
- Isolated nodes (no links) are visible on the periphery

**Dependencies** are installed automatically by `uv` on first run (`networkx`, `matplotlib`). No manual install needed.

---

## Roadmap

### Done
- [x] Core vault structure and schema
- [x] Claude Code save skill (loci-save)
- [x] vault_init, uid_generator, slug, write_file tools
- [x] MCP server — local stdio transport, Claude Desktop integration
- [x] patch and delete operations
- [x] Field dictionary — authoritative schema in vault meta, skill reads at runtime
- [ ] Schema versioning — seed files in loci-skill/references/, meta_version in config.yml
- [ ] rclone sync layer — provider-agnostic vault sync
- [ ] SSE transport — remote MCP server support (Claude.ai / mobile)
- [ ] deploy/ — systemd + nginx templates for server deployment
- [x] Docker image — containerize MCP server with vault as a mounted volume
- [x] Graph layer — NetworkX in-memory index for traversal and relationship queries
- [x] loci-query skill — retrieve, relate, and summarize knowledge across vault nodes
- [x] Asset registry — binary/rich file storage (HTML, PDF, PNG, etc.) with crash-safe write sequence, resolver, and startup recovery

### Next
- [ ] Testing suite — vault_init correctness, schema validation, duplicate detection, ingestion edge cases
- [ ] Streamable HTTP transport (SSE is deprecated in MCP spec)

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

## Testing

See [docs/testing.md](docs/testing.md) for how to run tests, add cases, and understand the fixture vault.

---

## Contributing

Coming soon.
