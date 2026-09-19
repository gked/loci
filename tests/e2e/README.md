# Browser E2E Suite

Playwright (Python binding) driving the real React app against a real FastAPI
backend and a real vault. No mocks — if these pass, the stack works.

## Running

```bash
make e2e-install     # once: downloads the Chromium binary
make test            # everything: unit + e2e
make test-e2e        # browser suite only
make test-fast       # unit only — no Node, no browser needed
```

Debugging:

```bash
uv run pytest tests/e2e/ --headed          # watch the browser
uv run pytest tests/e2e/ --slowmo 500      # slow it down
uv run pytest tests/e2e/ --tracing=on      # record traces
npx playwright show-trace test-results/**/trace.zip
```

## How a run works

```
e2e_vault ──► api_server ──► web_server ──► base_url ──► app_page
(temp vault)  (uvicorn)      (vite preview)  (origin)     (loaded page)
```

All server fixtures are **session-scoped** — the vault is built and both
processes start once for the whole run (~5s overhead, then ~1s/test).

1. **`e2e_vault`** copies `../fixtures/vault/` to a temp dir, overlays
   `../fixtures/e2e-overlay/`, writes `assets/e2e-sample.txt` beside the vault,
   and rewrites all dates (see below).
2. **`api_server`** starts uvicorn on an ephemeral port with
   `LOCI_VAULT_ROOT` pointed at that vault. `load_config()`
   (`src/loci/tools/vault_init.py:47`) honours the env var over `config.yml`, so
   your real vault is never touched.
3. **`web_server`** runs `vite build` then `vite preview`, with
   `LOCI_API_URL` set so `app/vite.config.js` proxies `/api` to the API server.
   Preview rather than dev: tests the shipped bundle, no HMR websocket noise.
   It invokes `app/node_modules/.bin/vite` directly — **not** `npm run …`, which
   would not forward signals to vite and would leave it holding the port after
   teardown. Missing `node_modules` fails the run rather than skipping it.
4. **`app_page`** returns a page already loaded and showing node rows.

## Running against a deployment

```bash
LOCI_E2E_BASE_URL=https://loci.example.com uv run pytest tests/e2e/ -m "not fixture_bound"
```

Both server fixtures no-op and the remaining specs run unchanged against that
origin.

**`-m "not fixture_bound"` is required, not optional.** Most of the suite
asserts on the e2e fixture vault — exact counts from `vault_facts.py`, overlay
uids like `e2e00002`, the mnemonic uids the navigation specs open — and none of
that exists on a real deployment. Those specs carry the `fixture_bound` marker:
all of `test_fixture_composition.py`, `test_filtering.py`,
`test_navigation.py`, and `test_frontmatter_parsing.py`, plus
`test_smoke.py::test_overlay_fixtures_present` and
`::test_recent_endpoint_is_populated`.

What is left is genuinely deployment-portable: the error and empty states in
`test_errors.py`, and the smoke specs that derive their expectation from the
API response rather than from a constant.

**When you add a spec that reads `vault_facts` or hardcodes a fixture uid, mark
it `fixture_bound`.**

## Traps

### 1. Dates are rewritten on every run — don't hardcode them

`nx_graph.recent()` filters on `updated_at >= now - 30 days`. The checked-in
fixture vault carries static January 2026 dates, so as real time passes every
node falls outside the window and `/api/nodes/recent` returns `[]` — leaving
the Recent section and the palette's default list permanently empty.

`_freshen_dates()` in `conftest.py` stamps each node `now - N hours`, ordered
by **filename** so the result is deterministic — renaming a fixture file
reshuffles which node is "most recent". `test_smoke.py::
test_recent_endpoint_is_populated` guards it. Hourly steps, not daily: a day per
node capped the vault at 30 nodes and the 31st failed the assert in
`_freshen_dates` rather than anything real.

### 2. Many fixture uids cannot be opened

`api.get()` resolves a bare uid by matching `[0-9a-f]{8}` (`src/loci/api.py:194`).
14 of the 27 base fixture nodes use mnemonic uids with non-hex letters
(`srch0001`, `hub00001`, `spoke001`, `chain001`, `lang0001`, ...), so
`GET /api/nodes/{uid}` 404s and the detail pane stays empty.

**Never open a node with `.first`.** Use a uid from `vault_facts.OPENABLE_UIDS`.
This is a fixture defect, not an app bug — real vaults only contain generated
hex uids. `test_fixture_composition.py` carries a strict xfail documenting it.

### 3. The palette shows recent nodes until search resolves

`CommandPalette.jsx` renders `debouncedQ.length >= 2 ? searchResults :
recentNodes`, with a 150ms debounce. `fill()` returns immediately, so asserting
"a result is visible" passes against the *recent* list without search ever
running — and clicking it races the re-render.

Always wait for the expected uid: `[data-testid='palette-result'][data-uid='…']`.

### 4. Counts live in one place

`vault_facts.py` holds every expected count. `test_fixture_composition.py` is
the canary — change a fixture node and it fails first with a clear diff instead
of five UI specs failing with confusing off-by-N errors. Its docstring has a
one-liner that recomputes the numbers.

The type and tag specs compare the **whole** histogram, not just the keys
already listed, so adding a node with a new type or tag fails here too.

## Selectors

Production code carries `data-testid` on the seams only. The UI leans on
decorative Latin (`praeceptum · command`, `topologia · locorum chartæ`) and
style-driven markup, so text selectors break on every design pass.

| Testid | Where | Extra attributes |
|---|---|---|
| `vault-index` | `VaultIndex.jsx` | — |
| `node-row` | `VaultIndex.jsx` | `data-uid`, `data-state` (active/archived/ghost) |
| `type-filter` | `VaultIndex.jsx` | `data-type`, `data-active` — chips come from `/api/types`, so the set is the registry's |
| `subtype-strip` | `VaultIndex.jsx` | present only while a type with subtypes is selected |
| `subtype-filter` | `VaultIndex.jsx` | `data-subtype`, `data-active`, `data-count` (count within the current type × tag) |
| `row-subtype` | `VaultIndex.jsx` | the subtype label under a row's type |
| `toggle-ghost`, `toggle-archived` | `VaultIndex.jsx` | `data-active` |
| `index-empty` | `VaultIndex.jsx` | — |
| `rail-row` | `VaultRail.jsx` | `data-rail-id`, `data-active` |
| `rail-tag` | `VaultRail.jsx` | `data-tag`, `data-active` |
| `rail-count` | `VaultRail.jsx` | `data-count` |
| `app-version` | `VaultRail.jsx` | `data-version`; empty until `/api/health` resolves |
| `node-detail` | `NodeDetail.jsx` | `data-uid` |
| `node-detail-empty` | `NodeDetail.jsx` | shown while the node query is loading |
| `node-title`, `node-body`, `node-frontmatter`, `node-back` | `NodeDetail.jsx` | — |
| `fm-value` | `NodeDetail.jsx` | `data-field` |
| `node-asset` | `NodeDetail.jsx` | `data-mime`; only when the node resolves an asset |
| `node-asset-content` | `NodeDetail.jsx` | inlined text asset body |
| `command-palette`, `palette-input`, `palette-empty` | `CommandPalette.jsx` | — |
| `palette-result` | `CommandPalette.jsx` | `data-uid` |
| `graph-node` | `GraphView.jsx` | `data-uid`, `data-selected` |
| `api-error` | `App.jsx` | — |

Elements with a real accessible name (`aria-label="filter tags"`, placeholders)
use `get_by_role` / `get_by_placeholder` instead — no testid needed.

**When you add a testid, add it to this table.**

## Not covered yet

- **Graph view.** `GraphView.jsx` runs a force simulation with `alphaRef` decay,
  so assertions need a settle strategy — freeze it via the existing spacebar
  pause (`GraphView.jsx:45`) or poll for position stability. `data-testid=
  "graph-node"` is already in place for whoever picks this up.
- **Visual regression.** Deliberately out of scope: the design system animates
  (`--flow-dur`, `--bezel-dur`), so screenshot diffs would be chronically flaky.
  `test_screenshots.py` *captures* the README images from this same fixture
  vault, but asserts nothing about them — it skips unless
  `LOCI_CAPTURE_SCREENSHOTS=1`, so `make test` never runs it. Regenerate with
  `make screenshots` and commit what lands in `docs/images/`. Two things it has
  to work around: shots must avoid the asset-bearing overlay node, whose
  resolved path is a pytest tmp dir containing the local username, and captures
  are taken at 2x then resampled down rather than palette-quantized, which
  collapses the per-type dot colours into grey.
- **Writes.** The HTTP API is read-only (`CORSMiddleware` allows GET only), so
  there is no create/edit flow to test from the browser.

## `test_packaged_ui.py` runs its own server

Every other spec drives the developer layout: `vite preview` for the UI,
uvicorn for the API, a proxy between them. An installed wheel runs neither —
one process serves the compiled bundle out of the package and answers `/api` on
the same origin.

That spec therefore builds its own bundle and starts its own uvicorn with
`LOCI_STATIC_DIR` pointed at `app/dist`, standing in for `src/loci/static/`,
which `make wheel` populates. It deliberately does not reshape the shared
`api_server` / `web_server` fixtures, so nothing about the rest of the suite
changes. It sets `LOCI_API_TOKEN` to a known value, because the token the
server stamps into `index.html` is one of the things it asserts on.
