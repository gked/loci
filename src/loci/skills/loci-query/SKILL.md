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

Call `loci__list_vault` with no arguments. If it errors, read the error code:

**`LOCI_NOT_CONFIGURED`** — Loci has never been set up. Ask the user where their
vault should live, then call `loci__set_vault_root(path=<their answer>)` and
retry. No restart is needed. **Never guess a path and never offer a default** —
the vault holds everything they save, and a location they did not choose is one
they will never find again.

**`LOCI_VAULT_UNREACHABLE`** — the vault is configured but its directory is
missing right now, usually an unmounted drive or a sync folder that has not come
down yet. Name the missing path and ask whether to wait or to point Loci
elsewhere with `loci__set_vault_root`. **Do not create a new vault at that
path** — the real one is probably just offline.

**Anything else** — tell the user:

```
The Loci vault is not reachable.
```
Then relay the error text the tool returned verbatim — it names the cause and
the fix for this install (an unmounted path, a missing volume mount, no vault
configured yet). Do not substitute a setup command for it: `setup.py` only
exists in a local checkout, so it is wrong for a Docker or `uvx` install and
fails outright anywhere but that checkout directory. If there is no error text,
the MCP server itself is not connected — tell the user to check their MCP
client config and restart Claude Code / Claude Desktop.

If the result contains a `_notice` key, show it to the user as an FYI before proceeding — e.g.:
> FYI: Vault meta files were automatically updated to v2 (language and aliases fields added).

---

## Query Modes

Identify which mode fits the user's request, then follow that workflow.

---

### Mode 1 — Lookup: "what do I know about X?"

Use when the user names a specific topic, person, project, or concept.

1. Call `loci__search_vault(query=<keyword>)` to find matching nodes. By default this
   searches only active nodes; pass `state="archived"` to search archived content or
   `state=None` to search everything.
2. If multiple results: present the list and ask which one (or "all of them").
3. For each target node: call `loci__read_vault(path=<path>)` to read the full content.
4. Call `loci__query_neighbors(uid=<uid>)` to surface direct connections with their relation types and directions.
5. Present: the node content, then a "Connected to:" section listing neighbors with type, relation type, and direction (in/out).

**If the target node is type `topic`:** topics are graph hubs, so automatically continue into Mode 3 (neighborhood) without waiting to be asked — call `loci__query_related(uid=<uid>, depth=2)` and present the full neighborhood grouped by distance. The user's intent when looking up a topic is almost always "show me everything under this concept."

If no results found via search, tell the user clearly — do not invent content.

---

### Mode 2 — Browse: "show me all tasks" / "notes tagged python" / "open tasks in project X"

Use when the user wants a list filtered by one or more attributes.

`loci__find_nodes` supports any combination of:
- `type` — node type (task, book, note, project, …)
- `tag` — node must include this tag
- `status` — exact match (open, done, archived, …)
- `state` — lifecycle visibility; defaults to `"active"` (archived nodes are excluded
  automatically). Pass `state="archived"` to show only archived nodes. Pass `state=None`
  to include all nodes regardless of state.
- `due_before` / `due_after` — ISO date strings (YYYY-MM-DD)
- `created_after` / `updated_after` — ISO date strings
- `related_to` — UID; only return nodes connected to this node by any edge
- `language` — language code (en, ru, de, …)

1. Call `loci__find_nodes(...)` with the filters that match the user's request.
2. Present results as a concise list: `[type] title — summary`.
3. Offer to read any item in full: "Read one? Just say which."

If the request is ambiguous (e.g. no type or tag inferable), ask before calling.

**Library queries:**
- All books: `find_nodes(type="asset", tag="book")`
- All reading logs: `find_nodes(type="reading-log")`
- Reading logs for a specific book: `query_neighbors(uid=<book_uid>)` — look for `reading-log` neighbors via `is-based-on` relation
- In-progress reads: `find_nodes(type="reading-log")` then read each node to check `read_status` — `find_nodes` does not filter on custom fields like `read_status`

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

### Mode 7 — Recency: "what have I been thinking about lately?"

Use when the user asks about recent activity, recent thoughts, or what's been on their mind.

Signals: "lately", "recently", "what's been on my mind", "what have I been working on", "recent activity", "what did I do this week/month".

1. Call `loci__query_recent(days=30)` to get recently updated nodes.
2. If the result is empty, retry with `days=90`. If still empty, say so — don't invent activity.
3. Group by type and present as a structured activity summary:
   ```
   Recent activity (last 30 days):

   Tasks (5):
     [todo] Build loci-query skill — updated 2026-04-15
     [done] Add networkx to pyproject.toml — updated 2026-03-24

   Documents (2):
     Loci Test Framework Implementation Plan — updated 2026-04-16
   ```
4. After the summary, offer: "Want me to go deeper on any of these, or map the connections around a specific item?"

---

### Mode 8 — Insight: "what patterns or non-obvious connections do I have?"

Use when the user asks about patterns, bridges, or non-obvious connections across their vault.

Signals: "insight", "patterns", "non-obvious", "what bridges", "cross-domain", "what themes", "what connects across", "what am I not seeing".

1. Call `loci__query_insights()` to get cross-domain bridge nodes.
2. If the result is empty, say so: "No cross-domain bridges found yet — the vault may not have enough cross-domain links."
3. For the top 3–5 results, call `loci__query_neighbors(uid)` to see what each bridges.
4. Present as a list of observations:
   ```
   Cross-domain bridges in your vault:

   🔗 [document] Loci Asset Registry Design Spec
      technology-engineering ↔ personal-development
      Connected to 8 nodes across both domains

   🔗 [task] Build loci-query skill
      technology-engineering ↔ personal-development
      Connected to 4 nodes
   ```
5. Synthesize: write 2–3 sentences identifying the overarching pattern — what topics or themes are bridging across domains? This is the insight, not just the list.
6. End with a specific follow-on: "The [topic/node] seems to be the connective tissue between X and Y. Want me to read it in full and explore its connections?"

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
