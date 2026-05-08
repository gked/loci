# Inner Shell — UI Kit

The vault explorer. Where the user actually browses, reads, and traverses the knowledge graph.

**Register**: clinical, archival, IDE-adjacent. Neutral background; node-type colors do the semantic lifting.

**Components**

- `Sidebar.jsx` — vault navigator (types, recent, tags)
- `NodeList.jsx`, `NodeCard.jsx` — list and detail
- `NodeDetail.jsx` — frontmatter grid + body + relations rail
- `RelationChip.jsx`, `TypeChip.jsx`, `TagChip.jsx`
- `CommandBar.jsx` — ⌘K floating capsule (the one place blur is allowed)
- `GraphView.jsx` — minimal SVG topology preview
- `Composer.jsx` — save flow

Open `index.html` for an interactive vault session.
