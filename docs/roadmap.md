# Status and Roadmap

## Project status

Work in progress, and a personal one. The core is used every day; the edges are
uneven. What that means concretely:

| Area | State |
|---|---|
| Vault format, ontology, registries | Stable, in daily use |
| MCP server and skills | Stable, in daily use |
| Released wheel install | Stable, in daily use |
| Checkout setup (`setup.py`) | Stable |
| Web UI | In daily use, read-only. No editing yet |
| Test suite (unit + browser e2e) | Runs on every push and PR |
| Packaging and releases | `make release` cuts the tag; CI builds and publishes the wheel |
| rclone sync | **Partial.** Manual script only, no scheduling or conflict handling, no tests |

Nothing is deprecated or abandoned; the weak spots are just unfinished. Each is
also flagged where it is documented, so you don't have to remember this table.

---

## Roadmap

### Done

`[~]` marks something that exists and works, but is not finished or well tested.

- [x] Core vault structure and schema
- [x] `vault_init`, `uid_generator`, `slug`, `write_file` tools
- [x] MCP server: stdio transport, Claude Code / Claude Desktop integration
- [x] Patch and delete operations
- [x] Field dictionary: authoritative schema in vault meta, skill reads at runtime
- [x] Schema versioning: seed files in `src/loci/skills/references/`, `meta_version` in `config.yml`
- [~] rclone wrapper: manual `push` / `pull` / `bisync` script. No scheduling, no conflict handling, no tests
- [x] SSE transport: remote MCP server support (Claude.ai / mobile)
- [x] Graph layer: NetworkX in-memory index for traversal and relationship queries
- [x] `loci-save` and `loci-query` skills
- [x] Type and relation registries: machine-readable ontology, validated on write, linted after
- [x] Assets: crash-safe write sequence, resolver layer, startup recovery
- [x] Library support: `asset` nodes with `subtype: book`; `log` canonical type (one per read, supports re-reads)
- [x] Inbox: `loci-stage/` staging folder, two-phase scan → execute, per-category budgets, resumable plan file
- [x] `scan_directory` + `loci-ingest-directory`: catalogue files where they already live
- [x] Locations refactor Phase 1: `has_asset` list schema, scheme dictionary, SchemeRegistry, local resolver + dispatcher, lint, `find_nodes` scheme filters
- [x] Locations refactor Phase 2: external scheme resolvers (`url`, `google-drive`, `nextcloud`, `gmail`, and the rest)
- [x] Locations refactor Phase 5: `asset-registry/` collapsed into `has_asset` frontmatter
- [x] Web UI: React + Vite app over a FastAPI backend: vault index, type/tag filters, node reader, graph view, command palette
- [x] Browser e2e suite: Playwright driving the real app against a real backend and vault
- [x] CI + git hooks: `main` protected locally and on GitHub, both suites run on every push
- [x] Release pipeline: `make release` cuts the tag, CI builds the wheel (UI inside) and publishes it to a GitHub Release

### Next
- [ ] Streamable HTTP transport (SSE is deprecated in the MCP spec)
- [ ] Retire the vestigial `asset-registry/` directory from `vault_init`
- [ ] Editing from the UI (currently read-only)
- [ ] Real sync: scheduling, conflict handling, and tests for the rclone layer

### Later
- [ ] Vector DB: deferred until summaries exceed the context window. Revisit ChromaDB / LanceDB / Qdrant at that point
- [ ] Browser extension / bookmarklet
- [ ] Native mobile / desktop apps (local-first, SQLite backend)
- [ ] Telegram bot: bidirectional ambient interface

### Open questions
- Relationship inference: at what vault size does automatic inference become useful vs. noisy?
- Decay heuristics: what signals indicate a note is going stale?
- Journal privacy: separate encryption layer for private entries?
- Content editing model: edit in place, or new node linked via `supersedes` / `revisits`?
- History tracking: implicit (git log) or explicit (encoded in graph)?
