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
    subgraph Mac
        V_MAC["vault/"]
        W_MAC["launchd watcher\n(com.loci.sync.plist)"]
        RC_MAC["rclone"]
    end

    subgraph Remote["Remote Storage"]
        NC["Nextcloud"]
        DB["Dropbox"]
        GD["Google Drive"]
        OD["OneDrive"]
        S3["S3 / other"]
    end

    subgraph LabServer["Lab Server"]
        V_SRV["vault/"]
        W_SRV["systemd path watcher\n(loci-sync.path)"]
        RC_SRV["rclone"]
    end

    V_MAC -->|"change detected"| W_MAC
    W_MAC --> RC_MAC
    RC_MAC -->|"push"| NC
    RC_MAC -->|"push"| DB
    RC_MAC -->|"push"| GD
    RC_MAC -->|"push"| OD
    RC_MAC -->|"push"| S3

    NC -->|"pull"| RC_SRV
    DB -->|"pull"| RC_SRV
    GD -->|"pull"| RC_SRV
    OD -->|"pull"| RC_SRV
    S3 -->|"pull"| RC_SRV
    RC_SRV --> V_SRV
    V_SRV -->|"change detected"| W_SRV
    W_SRV --> RC_SRV
```
