# Type-Specific Frontmatter Fields

Add these fields to the base schema for each type. All base fields still apply.

---

## document
No additional required fields. Use for written content without external provenance — no source URL, author attribution, or publication date to track.
Optional:
```yaml
status: draft | evergreen | archived
```
Format descriptors belong in `tags`: #essay, #spec, #design-doc, #meeting-notes, #journal, #note, etc.

---

## bookmark
```yaml
source_url: <URL>                        # required
site_name: <from og:site_name or domain> # parsed from page
```

---

## article
```yaml
source_url: <URL>
author: <name or null>
published_at: <date or null>
highlights: []                           # list of key quotes or passages
```
Format belongs in `tags`: #book, #blog-post, #whitepaper, #research-paper, #news, #magazine, #video, #podcast, etc.

---

## conversation
```yaml
participants: []          # list of entity UIDs, person names, or model names
model: <e.g. claude-sonnet-4-6 or null for human conversations>
turns: <integer count>
platform: claude | chatgpt | human | other
```

---

## project
```yaml
status: active | paused | completed | abandoned
goals: []                # list of goal statements
milestones: []           # list of milestone descriptions
due_date: <date or null>
```

---

## task
```yaml
status: todo | in-progress | done | cancelled
due_date: <date or null>
priority: high | medium | low | null
assignee: <name or null>
```

---

## event
```yaml
start_at: <ISO 8601 datetime>
end_at: <ISO 8601 datetime or null>
location: <string or null>
organizer: <entity UID or name or null>   # who organised or hosted the event
participants: []          # entity UIDs or names
```

---

## entity
```yaml
subtype: person | organization | place   # required; organization covers companies, NGOs, institutions
website: <URL or null>
# Person-specific (optional):
role: <job title or null>
organization: <entity UID or name>
# Organization-specific (optional):
industry: <string or null>
founded_at: <year or null>
# Place-specific (optional):
address: <string or null>
located_in: <entity UID or name of containing place or null>   # e.g. city within a country
```

---

## procedure
Use tags for process category: #recipe, #workout, #protocol, #playbook, #tutorial
```yaml
steps: []                # ordered list of step descriptions
expected_outcome: <string>
inputs: []               # list of required inputs (ingredients, equipment, etc.)
duration_minutes: <integer or null>
```

---

## topic
```yaml
status: active | archived
parent_topic: <UID or null>    # for hierarchical topics
```

---

## reference
```yaml
source_url: <URL or external ID>
source_type: <external app name, e.g. jira, google-calendar, email>
external_id: <ID in the source system, e.g. PROJ-123>
metadata: {}             # key-value pairs from foreign-definitions schema
```

---

## Relation Types

Typed edges between vault nodes. Format: `{uid: <uid>, type: <relation-type>}`.
Use the most specific type that fits. Fall back to `relates-to` only when nothing else applies.

### Structural / Ownership
| type | definition |
|---|---|
| `belongs-to` | This item is owned by or lives inside a larger whole (task → project, note → topic). |
| `is-part-of` | This item is a structural sub-component of another (chapter inside a book, section inside a document). Use over `belongs-to` for content hierarchy. |
| `has-part` | Inverse of `is-part-of`. The current node contains the linked node as a component. |

### Provenance / Derivation
| type | definition |
|---|---|
| `is-based-on` | This item was derived from or builds directly on another (a note summarising an article; a draft based on a source). |
| `same-work-as` | Both nodes are different manifestations of the same underlying work — e.g. a preprint and its published version, or an original and its translation. Borrowed from openWEMI. |
| `supersedes` | This item replaces or updates an older node. The older node remains but is considered deprecated. Borrowed from openWEMI. |
| `version-of` | This item is a revision or variant of another without fully replacing it (draft v2 alongside draft v1). |

### Semantic
| type | definition |
|---|---|
| `about` | This node is primarily about another node. Especially: an article or note → a topic node. Borrowed from schema.org. |
| `mentions` | This node references another in passing, without being primarily about it. Lighter than `about`. Borrowed from schema.org. |
| `influences` | One node shapes, informs, or has affected the direction of another. |
| `supports` | Provides evidence, reasoning, or examples for a claim made in another node. |
| `contradicts` | Challenges, refutes, or conflicts with the content of another node. |
| `inspired-by` | Conceptually sparked by another node, but not a direct derivation. |

### Generic
| type | definition |
|---|---|
| `relates-to` | Unspecified bidirectional connection. Use only when no other type fits. |
