// Sample vault data — denser graph for visualisation
const VAULT = [
  // ── Loci project cluster ──────────────────────────────
  { uid: "a1b2c3d4", type: "project", title: "Loci", status: "active", created: "2026-02-14", updated: "2026-04-25",
    tags: ["pkm","graph"], domains: ["technology-engineering"],
    body: "Personal knowledge management system built on plain Markdown files with YAML frontmatter, organised as a traversable knowledge graph. Designed to be accessed by both you and LLM agents.\n\nEvery piece of content saved becomes a structured node: a stable UID, typed relationships to other nodes, semantic metadata, and a place in a consistent folder structure.",
    relations: [
      { uid: "e9f7d201", type: "has-part" },
      { uid: "7a3b09cc", type: "has-part" },
      { uid: "33de77a1", type: "has-part" },
      { uid: "12fe44a0", type: "about" },
      { uid: "b6c80fde", type: "is-based-on" },
      { uid: "82f0aa1c", type: "inspired-by" },
    ]
  },
  { uid: "e9f7d201", type: "document", title: "Asset registry — design spec", status: "evergreen", created: "2026-03-21", updated: "2026-04-16",
    tags: ["design-doc","architecture"], domains: ["technology-engineering"],
    body: "Resolver layer that decouples vault nodes from physical file locations. Each registry entry is a YAML file keyed by UID; the manifest is a flat list. Vault nodes reference assets by setting has_asset: true; the registry maps UIDs to physical file locations.\n\nIf a file moves, only the registry entry changes. Vault nodes are untouched.",
    relations: [{ uid: "a1b2c3d4", type: "belongs-to" }, { uid: "12fe44a0", type: "about" }]
  },
  { uid: "7a3b09cc", type: "task", title: "Add networkx to pyproject.toml", status: "done", created: "2026-03-22", updated: "2026-03-24",
    tags: [], domains: ["technology-engineering"],
    body: "Required for graph traversal. Install via uv add networkx.",
    relations: [{ uid: "a1b2c3d4", type: "belongs-to" }, { uid: "12fe44a0", type: "supports" }]
  },
  { uid: "12fe44a0", type: "topic", title: "Graph databases", status: "active", created: "2026-01-10", updated: "2026-04-02",
    tags: ["graph","databases"], domains: ["technology-engineering"],
    body: "Graphs as a first-class data model. NetworkX for in-memory traversal; Kuzu / Neo4j for persistence; Cypher as the query language. The bridge between vault structure and agent reasoning.",
    relations: [{ uid: "b6c80fde", type: "relates-to" }, { uid: "55d10cc2", type: "relates-to" }]
  },
  { uid: "b6c80fde", type: "article", title: "Attention is all you need", status: null, created: "2025-11-04", updated: "2025-11-04",
    tags: ["whitepaper","ml"], domains: ["technology-engineering"],
    body: "Vaswani et al. The transformer architecture: self-attention without recurrence. Foundational for modern LLMs.",
    relations: [{ uid: "55d10cc2", type: "about" }]
  },
  { uid: "55d10cc2", type: "topic", title: "Transformers", status: "active", created: "2025-10-22", updated: "2026-04-01",
    tags: ["ml","architecture"], domains: ["technology-engineering"],
    body: "Self-attention based neural architectures.",
    relations: [{ uid: "12fe44a0", type: "relates-to" }]
  },
  { uid: "33de77a1", type: "conversation", title: "Vault topology — design discussion", status: null, created: "2026-04-12", updated: "2026-04-12",
    tags: ["design","claude"], domains: ["technology-engineering"],
    body: "Conversation with Claude about the right shape of the topology graph. Decided on bidirectional edges with one canonical direction stored, derived inverses computed at read time.",
    relations: [{ uid: "a1b2c3d4", type: "belongs-to" }, { uid: "12fe44a0", type: "about" }, { uid: "e9f7d201", type: "mentions" }]
  },
  { uid: "82f0aa1c", type: "bookmark", title: "Method of loci — Wikipedia", status: null, created: "2026-04-25", updated: "2026-04-25",
    tags: ["memory","reference"], domains: ["humanities"],
    body: "Mnemonic device, ancient. Place items at locations along a familiar route, then walk through to retrieve.",
    relations: [{ uid: "a1b2c3d4", type: "inspired-by" }, { uid: "44ac21ef", type: "mentions" }, { uid: "ff10aa44", type: "relates-to" }]
  },
  { uid: "10ee5503", type: "procedure", title: "Daily review — vault hygiene", status: null, created: "2026-03-01", updated: "2026-04-22",
    tags: ["protocol","journal"], domains: ["personal-development"],
    body: "Each morning: open inbox, classify untyped items, link to relevant topics, archive completed tasks.",
    relations: [{ uid: "a1b2c3d4", type: "supports" }]
  },

  // ── Stoicism cluster ───────────────────────────────────
  { uid: "44ac21ef", type: "entity", title: "Marcus Aurelius", status: null, created: "2025-09-12", updated: "2026-02-20",
    tags: ["philosophy"], domains: ["humanities"],
    body: "Roman emperor, 161–180 CE. Stoic philosopher; author of Meditations.",
    relations: [{ uid: "9e1c2b04", type: "influences" }, { uid: "ee44bb01", type: "has-part" }]
  },
  { uid: "9e1c2b04", type: "topic", title: "Stoicism", status: "active", created: "2025-08-01", updated: "2026-04-10",
    tags: ["philosophy"], domains: ["humanities"],
    body: "Hellenistic school of philosophy. Virtue is the only good; reason should govern emotion.",
    relations: [{ uid: "44ac21ef", type: "relates-to" }, { uid: "ff10aa44", type: "relates-to" }, { uid: "ee44bb01", type: "about" }]
  },
  { uid: "ee44bb01", type: "article", title: "Meditations — Book IV", status: null, created: "2025-09-15", updated: "2025-09-15",
    tags: ["book","philosophy"], domains: ["humanities"],
    body: "Personal writings of Marcus Aurelius on duty, mortality, and reason.",
    relations: [{ uid: "9e1c2b04", type: "about" }]
  },
  { uid: "ff10aa44", type: "topic", title: "Memory & rhetoric (antiquity)", status: "active", created: "2025-12-01", updated: "2026-03-30",
    tags: ["philosophy","rhetoric"], domains: ["humanities"],
    body: "The classical art of memory — Cicero, Quintilian, the Rhetorica ad Herennium.",
    relations: [{ uid: "9e1c2b04", type: "relates-to" }]
  },

  // ── Sourdough cluster (different domain — disconnected island) ──
  { uid: "c01baf81", type: "project", title: "Sourdough", status: "active", created: "2025-06-01", updated: "2026-04-20",
    tags: ["cooking"], domains: ["personal-development"],
    body: "Long-running baking project. Track hydration, schedule, results.",
    relations: [{ uid: "c1a01122", type: "has-part" }, { uid: "c1b033de", type: "has-part" }]
  },
  { uid: "c1a01122", type: "procedure", title: "75% hydration sourdough — base", status: null, created: "2025-06-10", updated: "2026-04-19",
    tags: ["recipe","baking"], domains: ["personal-development"],
    body: "Base recipe: 500g flour, 375g water, 100g levain, 10g salt. Bulk 4–5h, cold retard overnight.",
    relations: [{ uid: "c01baf81", type: "belongs-to" }, { uid: "c1b033de", type: "supports" }]
  },
  { uid: "c1b033de", type: "event", title: "Bake — 2026-04-19", status: null, created: "2026-04-19", updated: "2026-04-19",
    tags: ["log"], domains: ["personal-development"],
    body: "Fourth bake at 75% hydration. Better ear, slightly under-fermented.",
    relations: [{ uid: "c01baf81", type: "belongs-to" }]
  },
];

window.VAULT = VAULT;
