# Development

Working on Loci itself: the layout of the checkout, the daily commands, testing, and how a release is cut. For installing it to *use*, see [setup.md](setup.md). The binding working agreement — packaging rules, the skill ↔ tool sync rule, branch and PR rules — is [CLAUDE.md](../CLAUDE.md); this page is the tour, that one is the contract.

---

## Project Structure

```
loci/
  app/                              ← React + Vite frontend
    src/
      App.jsx
      components/                   ← VaultIndex, NodeDetail, GraphView, CommandPalette, …
      lib/api.js                    ← fetch layer for the FastAPI backend
    design/                         ← design system (tokens, assets, UI kit components)
      SKILL.md                      ← Claude's instructions for design work
      colors_and_type.css
      ui_kits/                      ← outer-shell, instrument-shell, inner-shell
      assets/

  src/loci/                         ← the installed package; everything here ships
    __init__.py
    api.py                          ← public facade, single entry point for all callers
    http_server.py                  ← FastAPI backend for the web UI; `loci` entry point
    mcp_server.py                   ← MCP tool definitions and docstrings; `loci-mcp` entry point
    skill_assembly.py               ← read_skill: packaged procedure + the user's overlay
    skills_install.py               ← `loci skills`: writes the stubs into ~/.claude/skills/
    skills/
      loci-save/SKILL.md            ← saving content
      loci-query/SKILL.md           ← querying and traversal
      loci-inbox/SKILL.md           ← processing loci-stage/
      loci-ingest-directory/SKILL.md ← cataloguing a directory in place
      references/                   ← source of truth for vault/ seed files
        <skill>-user.md             ← skill overlay seeds → vault/skills/<skill>.md
                                       (seeded once, user-owned)
        ontology.yaml               ← type system (TypeRegistry source)
        ontology-user.yaml          ← user type extensions (seeded once, user-owned)
        relation-dictionary.yaml    ← relation vocabulary (RelationRegistry source)
        relation-dictionary-user.yaml ← user relation extensions (seeded once, user-owned)
        scheme-dictionary.yaml      ← location scheme vocabulary (SchemeRegistry source)
        scheme-dictionary-user.yaml ← user scheme extensions (seeded once, user-owned)
        type-dictionary.md          ← type selection guide
        type-decision.md            ← type decision flowchart
        field-dictionary.md         ← field guidance per type
        tag-dictionary.md           ← seed: initial tag vocabulary
        relation-dictionary.md      ← seed: typed edge vocabulary (human-readable)
        foreign-definitions.md      ← seed: external source schemas
        ontology-guide.md           ← seed: the user's guide to the ontology
        ontology-system.md          ← developer guide to the registries (not seeded)
    tools/                          ← core business logic
      uid_generator.py
      slug.py
      vault_init.py                 ← folder structure, meta seeding, META_VERSION
      write_file.py                 ← node writes + registry validation
      vault_linter.py               ← lint checks for vault nodes (incl. has_asset structure)
      nx_graph.py                   ← NetworkX in-memory graph index
      type_registry.py              ← TypeRegistry singleton (ontology.yaml)
      relation_registry.py          ← RelationRegistry singleton (relation-dictionary.yaml)
      scheme_registry.py            ← SchemeRegistry singleton (scheme-dictionary.yaml)
      resolvers/                    ← location scheme resolver layer
        base.py                     ← Resolver ABC (resolve / enumerate interface)
        dispatcher.py               ← routes locations to a resolver by scheme
        local_resolver.py           ← local filesystem
        url_resolver.py             ← http/https
        external_resolver.py        ← pass-through pointer for cloud/remote schemes
      asset_registry.py             ← asset path helpers + crash-recovery intent files
      metadata_extractor.py         ← epub OPF parsing, PDF metadata, filename fallback
      inbox_scanner.py              ← classify files in loci-stage/ by extension and location
      inbox_plan.py                 ← read/write/update .inbox-plan.yaml work queue
      directory_scanner.py          ← catalogue an arbitrary directory in place

  tests/                            ← outside the package, so it never ships
    conftest.py
    fixtures/vault/                 ← base fixture vault (node files only, no meta/)
    fixtures/e2e-overlay/           ← extra nodes layered on top for e2e only
    test_*.py                       ← unit suite
    e2e/                            ← Playwright browser suite (see its README.md)

  .githooks/                        ← pre-commit / pre-merge-commit / pre-push (make hooks)
  .github/workflows/test.yml        ← CI: unit + e2e on every push and PR
  .github/workflows/release.yml     ← fires on a v* tag: verify, build the wheel, publish

  scripts/
    release.py                      ← make release / release-bump / release-publish
    release_notes.py                ← the "Upgrading" section of a release's notes
    run_preflight.py                ← config checks make run does before starting

  docs/
    problem.md                      ← why Loci exists
    setup.md                        ← wheel and checkout; sync
    usage.md                        ← mental model, scenarios, saving, querying, the UI
    examples.md                     ← one prompt per scenario
    ontology.md                     ← registries and schema versioning (repo side)
    development.md                  ← this file
    roadmap.md                      ← status table and roadmap
    execution-flows.md
    diagrams.md
    file-saving.md                  ← assets/, loci-stage/, and the file→node pipeline
    testing.md
    images/                         ← screenshots (`make screenshots`)

  sync/
    rclone.conf.sample              ← rclone remote config template
    sync.sh                         ← push/pull/bisync wrapper

  setup.py                          ← checkout setup wizard (the wheel uses `loci skills` + `claude mcp add`)
  run_server.sh
  config.sample.yml                 ← template for ~/.config/loci/config.yml
  dev-config.yml                    ← scratch config for `make dev` (gitignored)
  dev-vault/                        ← scratch vault for `make dev` (gitignored)
  dev-vault-seed/                   ← 500 generated nodes dev-vault/ is created from
  Makefile
  pyproject.toml
  CLAUDE.md                         ← working rules for Claude in this repo
  README.md
```

---

## Working on it

### One-time per clone

```bash
make hooks          # install .githooks/, blocking direct commits/merges/pushes
make e2e-install    # download the Chromium binary for the browser suite
```

### Running

```bash
make run            # real vault:  API (:8765) + built UI (:4173) together
make run-api        # FastAPI only:  uv run uvicorn loci.http_server:app --port 8765
make run-ui         # UI only:       cd app && npm run build && npm run preview
make dev            # scratch vault:  API (:8765) + Vite dev server (:5173) together
make dev-api        # FastAPI only:  uv run uvicorn loci.http_server:app --reload --port 8765
make dev-ui         # Vite only:     cd app && npm run dev
./run_server.sh     # MCP server in stdio mode (Claude Code / Claude Desktop)
```

### The two console scripts

Loci installs as a package named `loci` and ships two commands. They are
deliberately separate processes:

```bash
loci-mcp            # stdio MCP server — the MCP client spawns and kills this
loci                # the HTTP API (127.0.0.1:8765 by default; --host/--port to change)
```

`loci-mcp` takes no arguments: whichever client starts it owns the config file
it is launched from, so there is nowhere for you to pass a flag. Transport comes
from `LOCI_TRANSPORT` (`stdio`, or `sse` for a remote server).

`loci` mounts `/api/*` and, when a built bundle sits at `src/loci/static/`,
serves the frontend from the same process — which is how an installed wheel has
a UI at all. In a checkout that directory is absent until `make wheel` fills it,
so the UI runs separately via `make dev-ui` or `make run-ui`. Note that the
bundle a wheel build leaves behind is gitignored but not cleaned up: once you
have run `make wheel`, `uv run loci` keeps serving that frozen copy until the
next build replaces it.

Folding the two into one process would mean Claude Desktop's quit takes the API
down with it, and one web server per connected client. In a checkout, run
them through uv — `uv run loci`, `uv run loci-mcp` — or use the `make`
targets above.

The `dev` targets run against `dev-config.yml` and `dev-vault/` in the project
root, both gitignored and created on first use, so a stray `make dev` cannot
write into the vault you keep real notes in. `./run_server.sh` and an installed
server use the config file proper.

`dev-vault/` is created as a copy of `dev-vault-seed/` — 500 generated nodes,
committed, so the UI comes up populated at the size a real vault has rather
than blank. It is copied once; delete `dev-vault/` to start over from the seed.
The seed is what ships; `scripts/dev_seed.py` regenerates it after an ontology
change (`uv run python scripts/dev_seed.py --out dev-vault-seed --force`), and
`tests/test_dev_seed.py` fails if the two ever disagree or the seed stops
linting clean.

The `run` targets are the other half of that split: they set no `LOCI_CONFIG` or
`LOCI_VAULT_ROOT`, so both halves read `~/.config/loci/config.yml` and serve the
vault you actually keep notes in, with the built bundle rather than the dev
server. They run a preflight first — a missing config, a config with no
`vault_root`, or a `vault_root` that is not on disk (an unmounted drive, a sync
folder that has not come down) stops with that path named, instead of starting
up and serving an empty graph.

### Testing

```bash
make test           # full suite: Python unit + browser e2e
make test-fast      # unit only (-m "not e2e"), no Node or browser
make test-e2e       # browser suite only
make test-cov       # unit suite with a coverage report
make screenshots    # recapture the README/docs images from the e2e fixture vault
```

Tests point at a temp copy of `tests/fixtures/vault/` via the `LOCI_VAULT_ROOT` env var (set by the `tmp_vault` fixture in `conftest.py`), so your real vault is never touched. See [docs/testing.md](testing.md) and [tests/e2e/README.md](../tests/e2e/README.md).

### Releasing

A release is a tag plus a wheel on a
[GitHub Release](https://github.com/gked/loci/releases). One command does all
of it:

```bash
make release BUMP=patch|minor|major
```

It bumps the version, opens the PR, waits for that PR's checks, merges it,
pulls `main`, and pushes the tag — so it blocks for as long as the e2e suite
runs. `main` is still never written to by hand: the version change lands as a
PR like every other change. What is automated is the waiting and the merge.

It starts from a clean, up-to-date `main` and refuses otherwise, and it needs
`gh` installed and authenticated. `BUMP` has no default, because whether a
release is a patch or a minor is the one judgement the script leaves to you.

**The wait is not a formality.** `main` has no branch protection — the repo is
private on a free plan, so GitHub will not enforce required checks — which
means nothing server-side would refuse a merge on a red build.
`wait_for_checks()` in `scripts/release.py` is the only thing that does. If the
checks fail, nothing is tagged and the PR is left open.

The same release in halves, for when CI wants watching by hand or a one-step
run died partway:

```bash
make release-bump BUMP=minor       # opens the version-bump PR, then stops
# merge the PR, then:
git checkout main && git pull
make release-publish               # tags the merged commit and pushes the tag
```

#### What the bump touches

Two files: the version in `pyproject.toml`, and the version `uv.lock` records
for the local `loci` package. Both, because `uv run` re-resolves the lock the
moment those disagree — and the first command to run `uv run` after a bump PR
was `make release-publish` itself, which dirtied the tree its own clean-tree
guard then refused to act on. `release.py` runs `uv lock` as part of the bump,
and `test_the_repos_lockfile_agrees_with_pyproject` guards it.

#### What the tag sets off

Pushing `vX.Y.Z` fires [`.github/workflows/release.yml`](../.github/workflows/release.yml):

1. **Verify.** `scripts/release.py check <tag>` refuses to build unless the tag
   matches `pyproject.toml`. That is what makes a tag that lies about its
   version impossible — the failure mode that let `version = "0.1.0"` sit
   unchanged for 141 commits.
2. **Test.** The unit suite. The e2e suite already ran on the commit the tag
   points at, so running the browser again against an unchanged tree would cost
   minutes and add no signal.
3. **Build.** `make wheel`, never a bare `uv build`: it compiles `app/` into
   `src/loci/static/` first, so the wheel carries the UI. `app/` is not
   packaged, and an installed Loci has neither it nor Node to build it with.
4. **Publish.** `scripts/release_notes.py` writes the upgrade section, GitHub
   generates the merged-PR list beneath it, and the wheel is attached to the
   Release.

To build the wheel without releasing anything:

```bash
make wheel          # dist/*.whl, with app/ compiled into src/loci/static/
```

#### What the notes call out

`release_notes.py` diffs the release against the previous tag and opens the
notes with anything the user has to know about:

- **`META_VERSION` moved** → the vault's meta files reseed on the next start.
- **A skill's frontmatter changed, or a skill was added** → the stub in
  `~/.claude/skills/` is stale until they run `loci skills`. A change to the
  procedure below the frontmatter is served live by the MCP server and is not
  reported — there is no `skill_version` to bump.

Nothing has to be done by hand for that, which is exactly why `META_VERSION`
must be bumped in the same PR as the change it describes — the notes can only
report what the diff contains.

### Contributing rules

`main` is never written to directly. Every change lands through a PR from a branch, and the git hooks enforce it locally. Every PR carries unit tests; anything that touches the UI also carries a Playwright e2e test. Both suites must be green before the PR opens. See [CLAUDE.md](../CLAUDE.md) for the full working agreement, including the skill ↔ tool sync rule.

---

## Design Decisions

Key decisions are documented in the Loci vault itself, in the requirements note for the project (`search_vault("locus requirements")`). If you are contributing or extending Loci, read that and [CLAUDE.md](../CLAUDE.md) first.
