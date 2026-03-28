# Loci Architecture Diagrams

---

## 1. High-Level Capture Flow

```mermaid
flowchart TD
    subgraph Clients
        CC["Claude Code\n(Mac, stdio)"]
        CAI["Claude.ai\n(mobile / web, SSE)"]
    end

    subgraph Local["Local Machine (Mac)"]
        MCP_L["MCP Server\n(stdio)"]
        API_L["api.py"]
        V_L["vault/"]
    end

    subgraph Server["Lab Server"]
        CF["Cloudflare"]
        NX["nginx"]
        MCP_R["MCP Server\n(SSE, systemd)"]
        API_R["api.py"]
        V_R["vault/"]
    end

    CC -->|"stdio"| MCP_L
    MCP_L --> API_L
    API_L -->|"read / write"| V_L

    CAI -->|"HTTPS"| CF
    CF --> NX
    NX -->|"proxy"| MCP_R
    MCP_R --> API_R
    API_R -->|"read / write"| V_R
```

---

## 2. Sync Flow

```mermaid
flowchart LR
    subgraph Docker["Lab Server (Docker)"]
        V["vault/"]
        RC["rclone\n(scheduled push)"]
    end

    subgraph Remote["Remote Storage"]
        NC["Nextcloud"]
        DB["Dropbox"]
        GD["Google Drive"]
        OD["OneDrive"]
        S3["S3 / other"]
    end

    V --> RC
    RC -->|"push (BACKUP_INTERVAL)"| NC
    RC -->|"push (BACKUP_INTERVAL)"| DB
    RC -->|"push (BACKUP_INTERVAL)"| GD
    RC -->|"push (BACKUP_INTERVAL)"| OD
    RC -->|"push (BACKUP_INTERVAL)"| S3
```
