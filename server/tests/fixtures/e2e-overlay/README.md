# e2e overlay nodes

Extra vault nodes layered on top of `../vault/` by the e2e suite only
(`server/tests/e2e/conftest.py` → `e2e_vault` fixture).

**Why these live here and not in `../vault/`:** the base fixture vault backs the
Python unit suite, and CLAUDE.md forbids reshaping it — adding archived or
asset-bearing nodes there would shift the counts that existing tests assert on.
The UI, however, has states the base vault cannot express:

| File | uid | Exercises |
|---|---|---|
| `e2e-archived-note.md` | `e2e00001` | `state: archived` → the "archived" toggle in `VaultIndex.jsx` |
| `e2e-asset-note.md` | `e2e00002` | `has_asset` → the asset block in `NodeDetail.jsx` |
| `e2e-ghost-parent.md` | `e2e00003` | relation to a uid with **no file** → ghost node, "ghost" toggle |

## Ghost nodes

`nx_graph._build()` calls `g.add_edge(uid, target_uid)` for every relation
(`server/tools/nx_graph.py:120`). NetworkX creates the target implicitly with no
attributes, so it has no `path` — which is exactly how the UI defines a ghost
(`App.jsx`: `n.path` falsy). `e2e-ghost-parent.md` points at `e2e0dead`, which
deliberately has no file. **Do not create `e2e0dead.md`** — that would delete the
only ghost in the vault and break `test_filtering.py`.

## Assets

`e2e-asset-note.md` uses the `local` scheme. `LocalResolver._resolve_path`
(`server/tools/resolvers/local_resolver.py:25`) resolves relative paths against
`loci_root`, which is `vault_root.parent` — so the conftest writes the asset to
`<tmp>/assets/e2e-sample.txt` alongside the vault, not inside it. The file is
small and `text/plain`, so `api.get()` inlines its content rather than returning
a path reference.

## Dates

Do not hardcode meaningful dates here. The conftest rewrites `updated_at` /
`created_at` on **every** node (base + overlay) to be relative to today —
see the `_freshen_dates` docstring for why.
