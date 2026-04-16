---
name: loci-query
description: >
  Query the Loci vault to retrieve, relate, and summarize knowledge. Use
  whenever the user asks what they know about a topic, wants to find notes or
  tasks, explore connections between items, or get a summary across related
  vault nodes. Triggers on: "what do I know about X", "find notes on Y",
  "show me everything related to Z", "summarize my notes on X", "how is X
  connected to Y", "show all tasks", "what's linked to this",
  "what do I know about X and Y", "what connects X and Y".
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
4. Call `loci__query_neighbors(uid=<uid>)` to surface direct connections with their relation types and directions.
5. Present: the node content, then a "Connected to:" section listing neighbors with type, relation type, and direction (in/out).

If no results found via search, tell the user clearly — do not invent content.

---

### Mode 2 — Browse: "show me all tasks" / "notes tagged python" / "open tasks in project X"

Use when the user wants a list filtered by one or more attributes.

`loci__find_nodes` supports any combination of:
- `type` — node type (task, book, note, project, …)
- `tag` — node must include this tag
- `status` — exact match (open, done, archived, …)
- `due_before` / `due_after` — ISO date strings (YYYY-MM-DD)
- `created_after` / `updated_after` — ISO date strings
- `related_to` — UID; only return nodes connected to this node by any edge
- `language` — language code (en, ru, de, …)

1. Call `loci__find_nodes(...)` with the filters that match the user's request.
2. Present results as a concise list: `[type] title — summary`.
3. Offer to read any item in full: "Read one? Just say which."

If the request is ambiguous (e.g. no type or tag inferable), ask before calling.

---

### Mode 3 — Neighborhood: "what's connected to X?" / "show me everything around Y"

Use when the user wants to explore connections from a node.

1. Find the node via `loci__search_vault(query=<keyword>)`.
2. Call `loci__query_related(uid=<uid>, depth=2)`.
3. The result may be large. Use judgment to select what to surface:
   - Read titles and types from the result (no full reads yet).
   - Select the subset most relevant to the user's query based on title, type, and distance.
   - Prefer distance=1 nodes and nodes whose titles are topically close to the query.
   - Hard cap: read at most 8 nodes in full in a single response.
4. Group selected results by distance:
   ```
   Direct connections (distance 1):
     [task] Add networkx to pyproject.toml — belongs-to
     [document] Planning: Claude.ai Remote MCP — belongs-to

   2 hops away (distance 2):
     [project] loci
   ```
5. If results were trimmed, say so: "Showing X of Y connected nodes. Want me to explore a specific branch?"
6. Offer to read any node or go deeper on a branch.

---

### Mode 4 — Summarize: "summarize my notes on X"

Use when the user wants a synthesized view across multiple related nodes.

1. Find the anchor node via `loci__search_vault(query=<keyword>)`.
   If no anchor, use `loci__find_nodes(tag=<tag>)` or `loci__find_nodes(type=<type>)`.
2. Call `loci__query_related(uid=<uid>, depth=2)` to find the neighborhood.
3. From the result, select the nodes most relevant to the user's query based on title, type, and distance — do not read all of them. Hard cap: 8 full reads per response. Prefer distance=1 and topically close nodes.
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
4. If no path exists, automatically fall back to shared-neighbor search:
   - Call `loci__query_related(uid=<uid1>, depth=2)` and `loci__query_related(uid=<uid2>, depth=2)`.
   - Intersect the two result sets by UID.
   - If shared nodes exist, present them:
     ```
     No direct path found. Both connect to:
       [topic] Graph databases (distance 2 from A, distance 1 from B)
     ```
   - If the intersection is empty, say: "No connection found between A and B within 2 hops."

---

### Mode 6 — Cross-topic: "what do I know about X and Y?"

Use when the query names two distinct topics and the user wants to explore both together.

Signals: "X and Y", "both X and Y", "X vs Y", "intersection of X and Y".

1. Extract both topics from the query.
2. Call `loci__search_vault` for each topic separately. If either returns multiple candidates, clarify before proceeding.
3. Call `loci__query_related(uid=<uid1>, depth=2)` and `loci__query_related(uid=<uid2>, depth=2)`.
4. Intersect the two result sets by UID — these are nodes reachable from both topics within 2 hops.
5. Present in three sections:

   ```
   Connects both (shared neighbors):
     [topic] Rationality — distance 1 from ML, distance 2 from Philosophy
     [note] On priors and belief updating — distance 2 from both

   ML neighborhood (X only):
     [article] Attention Is All You Need
     [note] Transformer intuition

   Philosophy neighborhood (Y only):
     [book] Meditations — Marcus Aurelius
     [topic] Stoicism
   ```

6. If the intersection is empty, say so and present the two neighborhoods side by side without a shared section.
7. Apply the same relevance judgment and 8-node read cap as Mode 3 — use summaries to select what to surface, don't read everything.

---

## Architecture note

`find_nodes` filters (status, due dates, related_to, language) were added in the NetworkX phase as explicit parameters. This approach has a natural ceiling — every new filter dimension grows the tool signature.

The intended endpoint is a graph query language (Cypher via Kuzu). When that migration lands, `find_nodes` and its parameter list will be replaced by a single `query_vault` tool that accepts a query string. The skill will construct queries instead of parameter lists, and the tool surface shrinks back to minimal.

Until then: use `find_nodes` for filtered enumeration. Do not work around it in-skill by reading nodes individually and filtering in memory.

---

## General rules

- **Never invent content.** Only report what is in vault files.
- **UIDs are stable identifiers.** Always pass the uid (not the title) to graph tools.
- **Read before summarizing.** Do not summarize from the graph node attributes alone — always call `loci__read_vault` for the full content.
- **Offer next steps.** After any query result, suggest a natural follow-on action (read a node, go deeper, save a new document from the synthesis).
- **Signal low confidence, not high.** Do not add confidence labels to every claim. Only flag when a synthesis draws primarily from distance=2 nodes or from summaries alone without full reads — add a single closing line such as: "Note: some of this is inferred from loosely connected nodes — worth verifying by reading the source files."
