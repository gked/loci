# Loci Execution Flows

---

## 1. Brand New Installation

### 1.1 Python Project (`setup.py`)

```
git clone <repo>
uv run setup.py
  │
  ├─ uv sync                          # install deps into .venv
  │
  ├─ vault_init()                     # create vault/ skeleton if absent
  │
  ├─ register_mcp_claude_code()
  │    └─ claude mcp add --scope user loci uv -- run --directory <project> loci-mcp
  │         → writes entry to ~/.claude.json
  │
  ├─ register_mcp_claude_desktop()
  │    └─ writes mcpServers.loci entry into
  │         ~/Library/Application Support/Claude/claude_desktop_config.json
  │
  └─ install_skill_stubs()            # loci.skills_install
       └─ ~/.claude/skills/loci-save/SKILL.md   # stub: packaged frontmatter over
       └─ ~/.claude/skills/loci-query/SKILL.md  #   "call loci__read_skill and follow it"
       └─ ... one per src/loci/skills/<name>/   # read_skill serves the procedure
                                                #   + vault/meta/<name>-user.md

User restarts Claude Code / Claude Desktop
Claude Code spawns:  uv run loci-mcp  (stdio transport)
```

### 1.2 Docker (`setup-homelab.sh`)

```
bash deploy/setup-homelab.sh
  │
  ├─ install_docker()                  # curl get.docker.com
  ├─ install_rclone()                  # optional backup tool
  ├─ configure_rclone()                # interactive if BACKUP_REMOTE set
  ├─ install_cloudflared()             # Cloudflare tunnel binary
  ├─ setup_cloudflare_tunnel()
  │    ├─ cloudflared tunnel login
  │    ├─ cloudflared tunnel create loci
  │    ├─ write ~/.cloudflared/config.yml  (ingress → localhost:4444)
  │    ├─ cloudflared tunnel route dns
  │    └─ install + start cloudflared systemd service
  │
  ├─ setup_loci()
  │    ├─ git clone <repo> ~/loci
  │    ├─ mkdir ~/loci-vault
  │    └─ write deploy/.env  (VAULT_PATH, RCLONE_CONFIG, BACKUP_* vars)
  │
  └─ start_loci()
       └─ docker compose --env-file .env up -d --build
            │
            └─ Dockerfile build:
                 ├─ uv sync --frozen      # deps layer
                 ├─ copy app code
                 └─ ENTRYPOINT entrypoint.sh
                      ├─ (optional) background rclone sync loop
                      └─ uv run loci-mcp  (SSE transport, port 8000)

Host port mapping: localhost:4444 → container:8000
Cloudflare tunnel: https://<hostname>/sse → localhost:4444

User registers client:
  claude mcp add --transport sse loci https://<hostname>/sse --scope user
```

---

## 2. Update to Existing MCP

### 2.1 Python Project

```
git pull                               # fetch new code

uv run setup.py                        # safe to re-run (idempotent)
  │
  ├─ uv sync                           # picks up any new/changed deps
  │
  ├─ vault_init()                      # no-op if vault already initialized;
  │                                    #   applies migrations if version bumped
  │
  ├─ register_mcp_claude_code()        # re-registers with same command
  │                                    #   (overwrites existing ~/.claude.json entry)
  │
  ├─ register_mcp_claude_desktop()     # overwrites mcpServers.loci entry
  │
  └─ install_skill_stubs()             # rewrites any stub whose frontmatter
                                       #   changed; replaces a symlink from an
                                       #   older install with a stub

User restarts Claude Code / Claude Desktop
```

### 2.2 Docker

```
git -C ~/loci pull                     # or: cd ~/loci && git pull

cd ~/loci/deploy
docker compose --env-file .env up -d --build
  │
  ├─ Docker rebuilds image
  │    ├─ uv sync --frozen  (deps layer may be cached if uv.lock unchanged)
  │    └─ copies updated app code
  │
  └─ replaces running container in-place (compose recreates only changed service)

Vault data is untouched — mounted as external volume (VAULT_PATH)
Cloudflare tunnel and systemd service unchanged — no restart needed
```

---

## Summary

| | Python | Docker |
|---|---|---|
| Transport | stdio (Claude spawns process) | SSE (HTTP, always-on) |
| Vault location | `<project>/vault/` (default) | External volume (`VAULT_PATH`) |
| Client registration | `setup.py` handles it | Manual `claude mcp add --transport sse` |
| Updates | `git pull` + `uv run setup.py` | `git pull` + `docker compose up -d --build` |
