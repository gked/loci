# Loci Execution Flows

---

## 1. Brand New Installation

### 1.1 Python Project (`setup.py`)

```
git clone <repo>
python setup.py
  │
  ├─ uv sync                          # install deps into .venv
  │
  ├─ vault_init()                     # create vault/ skeleton if absent
  │
  ├─ register_mcp_claude_code()
  │    └─ claude mcp add --scope user loci uv -- run --directory <project> python loci_mcp/server.py
  │         → writes entry to ~/.claude.json
  │
  ├─ register_mcp_claude_desktop()
  │    └─ writes mcpServers.loci entry into
  │         ~/Library/Application Support/Claude/claude_desktop_config.json
  │
  └─ install_skill_symlinks()
       └─ ~/.claude/skills/loci-save  → <project>/loci-skill/loci-save
       └─ ~/.claude/skills/loci-query → <project>/loci-skill/loci-query

User restarts Claude Code / Claude Desktop
Claude Code spawns:  uv run python loci_mcp/server.py  (stdio transport)
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
                      └─ uv run python loci_mcp/server.py  (SSE transport, port 8000)

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

python setup.py                        # safe to re-run (idempotent)
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
  └─ install_skill_symlinks()          # replaces symlinks (unlink + re-link)

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
| Updates | `git pull` + `python setup.py` | `git pull` + `docker compose up -d --build` |
