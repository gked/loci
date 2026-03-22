# Type-Specific Frontmatter Fields

Add these fields to the base schema for each type. All base fields still apply.

---

## note
No additional required fields. Optional:
```yaml
status: draft | evergreen | archived
```

---

## article
```yaml
source_url: <URL>
author: <name or null>
published_at: <date or null>
format: article | book | paper | video   # carried by tag too
highlights: []                           # list of key quotes or passages
```

---

## conversation
```yaml
participants: []          # list of names or model identifiers
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
participants: []          # entity UIDs or names
```

---

## entity
```yaml
subtype: person | company | organization | institution   # carried by tag too
website: <URL or null>
# Person-specific (optional):
role: <job title or null>
organization: <entity UID or name>
# Company/org-specific (optional):
industry: <string or null>
founded_at: <year or null>
```

---

## procedure
```yaml
subtype: recipe | workout | protocol | playbook | tutorial   # carried by tag too
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
