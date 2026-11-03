# Loci Architecture Diagrams

---

## 1. Components

One vault, two processes. The MCP server and the web UI are separate processes
over the same `api.py` facade, so they cannot drift onto different code paths.

```mermaid
flowchart TD
    subgraph Agents["AI agents (MCP clients)"]
        CC["Claude Code / Claude Desktop"]
        OTHER["Other MCP clients\n(Codex, …)"]
    end

    Browser["Browser"]

    subgraph Local["Your machine"]
        MCP["loci-mcp\nMCP server (stdio)"]
        HTTP["loci\nFastAPI + built UI\n127.0.0.1:8765"]
        API["api.py\n(one facade)"]
        REG["Registries\ntypes · relations · schemes"]
        GRAPH["NetworkX graph index"]

        subgraph Root["Vault parent folder (loci_root)"]
            V["vault/\n*.md + meta/"]
            H["vault/.loci/history/\nchange history"]
            A["assets/"]
            S["loci-stage/\ninbox"]
        end
    end

    Remote["Remote storage\n(rclone, manual)"]

    CC -->|stdio| MCP
    OTHER -->|stdio| MCP
    Browser -->|HTTP, read-only| HTTP
    MCP --> API
    HTTP --> API
    API --> REG
    API --> GRAPH
    API -->|read / write| V
    API -->|one commit per write| H
    API -->|save / resolve| A
    API -->|scan / ingest| S
    V -.->|sync/sync.sh| Remote
```

## 2. A save, end to end

```mermaid
sequenceDiagram
    participant U as You
    participant Ag as Agent
    participant M as loci-mcp
    participant R as Registries
    participant V as Vault

    U->>Ag: "Save this article to my loci vault: <url>"
    Ag->>M: read_skill("loci-save")
    M-->>Ag: packaged procedure + your overlay
    Ag->>M: read_meta / find_nodes (ontology, link candidates)
    Ag-->>U: proposed type + links, ask to confirm
    U->>Ag: confirm
    Ag->>M: write_vault(frontmatter, body)
    M->>R: validate type, fields, relations
    R-->>M: ok (or reject unknown values)
    M->>V: write <slug>.md, record history commit
    M-->>Ag: uid, path
```
