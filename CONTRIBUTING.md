# Contributing to Loci

Loci is a personal project, built for one person's vault first. Issues and pull
requests are welcome, with two things worth knowing before you spend time on
something.

## Read this first: the licence is not open source

Loci is released under [PolyForm Noncommercial 1.0.0](LICENSE). Any
noncommercial use is free: personal use, research, teaching, charities. Any
business use needs a separate licence from the owner.

That restriction means Loci does **not** meet the Open Source Initiative's
definition, which forbids discriminating against commercial use. It is
source-available. Some people decline to contribute to such projects on
principle, and some employers forbid it outright. That is a reasonable position
and no hard feelings if it is yours.

## You must sign the CLA

Every pull request is gated on a signed [Contributor Licence Agreement](CLA.md).
A bot comments on your PR with the exact sentence to reply with; posting it
records your signature and turns the check green. You sign once, ever.

**You keep your copyright.** The CLA is a licence, not an assignment. Your
contribution stays yours to use, publish, or sell anywhere else on any terms.

What it grants the owner is the right to relicense the project as a whole,
which is what makes commercial licences possible and keeps a future move to
AGPL or MIT available. Without it, one merged PR would permanently remove both
options. The reasoning is spelled out in full in [CLA.md](CLA.md).

## Before you open a pull request

Read [CLAUDE.md](CLAUDE.md). It is written for an AI agent working in this
repository, but it is the honest description of how the project is built, and
the rules apply to everyone.

The parts that will get a PR sent back:

**Every change carries tests.** Unit tests in `tests/` for any behaviour
change. A PR with no test change is only acceptable for pure docs, comments, or
formatting.

**UI changes carry a browser test too.** If the change alters anything a user
sees or clicks in `app/`, it also needs a Playwright spec in
`tests/e2e/` that drives the real thing in Chromium. That includes
changes reaching the UI indirectly, such as an API response shape or a registry
value the UI renders.

**Both suites must be green.** `make test` runs unit and browser tests. CI
re-runs them on every push and pull request.

**Skills and tools stay in sync.** Touching `src/loci/tools/`, `src/loci/api.py`, or
`src/loci/mcp_server.py` usually means a matching change in
`src/loci/skills/`, and the reverse. CLAUDE.md has the checklist.

## Getting set up

```bash
make hooks          # once per clone: installs .githooks/
make skills-link    # symlink the skills into ~/.claude/skills/
make e2e-install    # once: downloads the Chromium binary
uv run setup.py     # configures the vault and registers the MCP server
make dev            # API on :8765, UI on :5173
make test           # unit + browser
```

`main` is never written to directly. Branch, open a pull request, let CI run.

## Reporting a bug

Include what you ran, what happened, and what you expected. If it involves the
vault, the output of `loci__lint_vault` is usually the fastest way to a
diagnosis. Please do not paste private vault content into an issue.

## Skills, while developing

`make skills-link` symlinks `src/loci/skills/<name>/` into `~/.claude/skills/`,
so editing a skill is live in Claude Code with nothing to re-run. (`make skills`
copies instead — that is what an installed wheel does, and what `loci skills`
does by default.)

Once `make hooks` is installed, `post-checkout` and `post-merge` re-run the
link whenever a branch switch or a pull changed anything under
`src/loci/skills/`. That covers the one thing a symlink cannot do for itself:
notice a skill directory someone else added. Set `LOCI_SKIP_SKILL_LINK=1` to
opt out.

## Cutting a release

A release is a git tag and a wheel attached to a GitHub Release. The version is
yours to choose — nothing infers it from commit messages — and it lands through
a PR like every other change, because `main` is never written to by hand.

```bash
make release BUMP=patch        # or minor, or major
```

That prints the commits since the last tag, shows the version change, and on
confirmation opens a PR that edits one line in `pyproject.toml`.

Once it has merged:

```bash
git checkout main && git pull
make release-publish           # tags the merged commit and pushes the tag
```

Pushing the tag triggers `.github/workflows/release.yml`, which:

1. refuses to continue unless the tag matches `pyproject.toml` — this is what
   catches a tag pushed before its bump PR merged;
2. runs the unit suite and builds the wheel with `make wheel` — which
   compiles the frontend into `src/loci/static/` first, because `uv build`
   alone ships a backend and an installed Loci has no Node to build a UI with;
3. composes the notes: an "Upgrading" section listing any `META_VERSION` or
   `skill_version` that moved since the previous tag, above GitHub's own list
   of merged PRs;
4. publishes the Release with the wheel and sdist attached.

The upgrade section is generated by `scripts/release_notes.py` and appears only
when something actually moved. A skill bump is the one that asks something of
the user — their copy in `~/.claude/skills/` is stale until they run
`loci skills` — so it must not be left to a PR title to convey.
