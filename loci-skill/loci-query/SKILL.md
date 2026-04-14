---
name: loci-query
description: >
  Query the Loci vault to retrieve, relate, and summarize knowledge. Use
  whenever the user asks what they know about a topic, wants to find notes or
  tasks, explore connections between items, or get a summary across related
  vault nodes. Triggers on: "what do I know about X", "find notes on Y",
  "show me everything related to Z", "summarize my notes on X", "how is X
  connected to Y", "show all tasks", "what's linked to this".
---

# Loci Query Skill

Retrieves and synthesizes content from the Loci vault using the graph layer.

---

## Step 0 — Verify vault is reachable

Call `loci__list_vault` with no arguments. If it errors, tell the user:

```
The Loci vault is not reachable. Please run:
  python setup.py
Then restart Claude Code / Claude Desktop.
```

If the result contains a `_notice` key, show it to the user as an FYI before proceeding — e.g.:
> FYI: Vault meta files were automatically updated to v2 (language and aliases fields added).

---

## Query Modes

Identify which mode fits the user's request, then follow that workflow.

---

### Mode 1 — Lookup: "what do I know about X?"

Use when the user names a specific topic, person, project, or concept.

1. Call `loci__search_vault(query=<keyword>)` to find matching nodes.
2. If multiple results: present the list and ask which one (or "all of them").
3. For each target node: call `loci__read_vault(path=<path>)` to read the full content.
4. Call `loci__query_related(uid=<uid>, depth=1)` to surface direct connections.
5. Present: the node content, then a "Connected to:" section listing related nodes with their type and relation type.

If no results found via search, tell the user clearly — do not invent content.

---

### Mode 2 — Browse: "show me all tasks" / "notes tagged python"

Use when the user wants a list filtered by type or tag.

1. Call `loci__find_nodes(type=<type>, tag=<tag>)` with the appropriate filters.
2. Present results as a concise list: `[type] title — summary`.
3. Offer to read any item in full: "Read one? Just say which."

If neither type nor tag is clear from the request, ask before calling.

---

### Mode 3 — Neighborhood: "what's connected to X?" / "show me everything around Y"

Use when the user wants to explore connections from a node.

1. Find the node via `loci__search_vault(query=<keyword>)`.
2. Call `loci__query_related(uid=<uid>, depth=2)`.
3. Group results by distance:
   ```
   Direct connections (distance 1):
     [task] Add networkx to pyproject.toml — belongs-to
     [document] Planning: Claude.ai Remote MCP — belongs-to

   2 hops away (distance 2):
     [project] loci
   ```
4. Offer to read any node or go deeper on a branch.

---

### Mode 4 — Summarize: "summarize my notes on X"

Use when the user wants a synthesized view across multiple related nodes.

1. Find the anchor node via `loci__search_vault(query=<keyword>)`.
   If no anchor, use `loci__find_nodes(tag=<tag>)` or `loci__find_nodes(type=<type>)`.
2. Call `loci__query_related(uid=<uid>, depth=2)` to find the neighborhood.
3. Call `loci__read_vault(path=<path>)` for the anchor and each closely related node (distance 1, or distance 2 if few results). Cap at ~8 nodes to stay focused.
4. Synthesize: write a coherent summary that integrates the content across nodes. Note where items agree, contradict, or extend each other.
5. End with: "Sources: [list of titles with UIDs]"

Do not fabricate content not present in the vault files.

---

### Mode 5 — Path: "how is X connected to Y?"

Use when the user wants to understand the relationship chain between two nodes.

1. Find both nodes via `loci__search_vault`.
2. Call `loci__query_path(uid_from=<uid1>, uid_to=<uid2>)`.
3. If a path exists, present it as a chain:
   ```
   [document] Planning doc → belongs-to → [project] loci → parent-of → [task] Add networkx
   ```
4. If no path exists, say so clearly. Offer to show the neighborhood of each node instead.

---

## General rules

- **Never invent content.** Only report what is in vault files.
- **UIDs are stable identifiers.** Always pass the uid (not the title) to graph tools.
- **Read before summarizing.** Do not summarize from the graph node attributes alone — always call `loci__read_vault` for the full content.
- **Offer next steps.** After any query result, suggest a natural follow-on action (read a node, go deeper, save a new document from the synthesis).
