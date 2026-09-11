# Updating an existing node

Read this when the user wants to correct or extend a node that already exists
rather than create a new one — "update X", "add a link to Y", "fix the
relations on Z", "mark that task done", "tag that document with X", or when a
save was refused as a duplicate and the user chose to update the existing item.

## U1 — Identify the target

Find the node: `loci__search_vault(query=<keyword>)` or
`loci__find_nodes(type=<type>, ...)`, then `loci__read_vault(path=<path or uid>)`
to read its current frontmatter and body. If several nodes could be the one,
show them and ask.

`path` accepts the node's 8-character UID as well as a file path — when you
already know the UID, pass it directly. The same is true of `loci__patch_vault`
and `loci__delete_vault`.

## U2 — Work out the new values

Patch **replaces** a field; it does not append. For every field that changes,
construct the complete new value from what is already there.

Example — adding a relation:

```
existing relations: [{uid: "a1b2c3d4", type: "belongs-to"}]
user wants to add:  {uid: "f9e8d7c6", type: "influences"}
new relations list: [{uid: "a1b2c3d4", type: "belongs-to"}, {uid: "f9e8d7c6", type: "influences"}]
```

### Temporal fields (entity type only)

Some entity fields describe a current state that changes over time. Archive the
old value before setting the new one:

- **`organization`** — append `{organization: <old value>, roles: <current roles>,
  from: <estimated or null>, to: <today>}` to `affiliations`, then set the new
  `organization`. If `roles` change with the org, update them too.
- **Any other temporal field** (`location`, `website`, …) — append
  `{field: <field name>, value: <old value>, from: <estimated or null>, to: <today>}`
  to `history`, then set the new value.
- **Body annotation** — append a line to a `## History` section at the bottom of
  the body (create the section if missing):

  ```
  - 2026-03-22: organization changed from University of Sussex to University of Manchester
  ```

  The body is **not** a frontmatter field. Read it with `loci__read_vault`,
  append the line, and pass the whole result as the separate `body=` argument
  in U4 — never inside `updates`.

## U3 — Confirm

Show what will change before patching:

```
Updating: 2026-03-21-my-document.md
  relations: adding link to [Project X] (f9e8d7c6)
Proceed? [yes / no]
```

## U4 — Patch

```
loci__patch_vault(path=<path or uid>, updates={<only changed frontmatter fields>})
```

If the body changed too — a `## History` line, or any other edit to the prose —
pass it as its own argument:

```
loci__patch_vault(path=<path or uid>, updates={...}, body=<full new body>)
```

`body` always carries the **complete** new body text, not a fragment. Putting it
inside `updates` writes it into the frontmatter as a quoted YAML scalar, and a
`---` line anywhere in it stops the node parsing at all. The tool reroutes a
misplaced `body` key and warns, but don't rely on that.

Confirm to the user:

```
Updated: <path>
Changed: <list of field names>
```

## Archiving and unarchiving

Archiving hides a node from graph queries and search by default:

```python
loci__patch_vault(path=<path>, updates={
    "state": "archived",
    "archived_at": "<ISO 8601 timestamp>",
})
```

Archived nodes are invisible to `loci__find_nodes` (which defaults to
`state="active"`) and to `loci__search_vault`; the user must ask for archived
content explicitly. To restore a node:

```python
loci__patch_vault(path=<path>, updates={
    "state": "active",
    "archived_at": None,
})
```

`state` is distinct from type-specific `status` fields (`task.status`,
`document.status`). A task can be `status: done` and `state: active` — visible
but finished — or `state: archived`, hidden from the graph entirely. Archive when
the node is no longer relevant day to day, not merely when its workflow is
complete.

## Deleting

Find the node, read it back to confirm it is the right one, then ask the user
explicitly before calling `loci__delete_vault`. Deletion is permanent — there is
no undo.
