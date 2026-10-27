.PHONY: test test-fast test-e2e test-cov cov-html e2e-install dev dev-api dev-ui
.PHONY: run run-api run-ui run-check hooks screenshots
.PHONY: skills wheel release release-bump release-publish

# One-time per clone: point git at the versioned hooks in .githooks/.
# They block commits, merges, and pushes that land directly on main.
hooks:
	git config core.hooksPath .githooks
	@echo "hooks installed (core.hooksPath = .githooks)"

# Full suite — Python unit tests + browser e2e. Needs `make e2e-install` once.
test:
	uv sync --extra dev
	npm ci --prefix app
	uv run pytest tests/ -v

# Everything except the browser suite. No Node or Playwright browser required.
test-fast:
	uv sync --extra dev
	uv run pytest tests/ -v -m "not e2e"

# Browser suite only.
test-e2e:
	uv sync --extra dev
	npm ci --prefix app
	uv run pytest tests/e2e/ -v

# One-time (and after Playwright upgrades): download the browser binary.
e2e-install:
	uv sync --extra dev
	uv run playwright install chromium

# Recapture the README/docs screenshots from the e2e fixture vault into docs/images/.
# Opt-in: these specs skip during a normal run. Commit the images afterwards.
screenshots:
	uv sync --extra dev
	npm ci --prefix app
	LOCI_CAPTURE_SCREENSHOTS=1 uv run --with pillow pytest tests/e2e/test_screenshots.py -v -s

test-cov:
	uv sync --extra dev
	uv run pytest tests/ --cov=loci --cov-report=term-missing -m "not e2e"

cov-html:
	uv sync --extra dev
	uv run pytest tests/ --cov=loci --cov-report=html:htmlcov -m "not e2e"
	open htmlcov/index.html

# Development runs against a scratch config and a scratch vault, never the real
# ones under ~/.config/loci. Both are gitignored and created on demand, so a
# stray `make dev` can't write into the vault you actually keep notes in.
DEV_CONFIG := $(CURDIR)/dev-config.yml
DEV_VAULT  := $(CURDIR)/dev-vault
DEV_VAULT_SEED := $(CURDIR)/dev-vault-seed

dev dev-api dev-ui: export LOCI_CONFIG = $(DEV_CONFIG)
dev dev-api dev-ui: export LOCI_VAULT_ROOT = $(DEV_VAULT)

# Only holds the API token. vault_root comes from LOCI_VAULT_ROOT above.
# Generated once; delete it to rotate.
#
# Written via a temp file so a failed generation leaves no target behind: an
# empty api_token still parses, so make would consider the file built and every
# later `make dev` would run tokenless against a 403ing API.
$(DEV_CONFIG):
	@token="$$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"; \
	if [ -z "$$token" ]; then \
		echo "could not generate an API token — is python3 on PATH?" >&2; \
		exit 1; \
	fi; \
	printf 'api_token: %s\n' "$$token" > $@.tmp && mv $@.tmp $@
	@echo "created $@ (gitignored)"

# ensure_env_vault() refuses to create a missing LOCI_VAULT_ROOT, since an
# absent directory is more likely a typo than a new vault. The directory is ours
# to make here; the server seeds it once it exists.
#
# It is created populated: an empty vault renders a blank graph, which reads as
# the app being broken. dev-vault-seed/ is 500 generated nodes, committed, and
# only copied on creation — delete dev-vault/ to start over from the seed.
# scripts/dev_seed.py regenerates the seed after an ontology change.
#
# Copied via a temp directory for the same reason $(DEV_CONFIG) is: make treats
# an existing directory as built, so a failed copy that left an empty dev-vault/
# behind would have every later `make dev` serve a blank vault without a word.
$(DEV_VAULT):
	@rm -rf $@.tmp && mkdir -p $@.tmp
	@cp $(DEV_VAULT_SEED)/*.md $@.tmp/ || { rm -rf $@.tmp; exit 1; }
	@mv $@.tmp $@
	@echo "created $@ from $(DEV_VAULT_SEED) (gitignored)"

# Both prerequisites are built here, before the sub-makes fork. Leaving them to
# dev-api and dev-ui let the two race on a clean checkout: each generated its own
# token, the API cached the first and vite baked in the second, and /api/open-local
# then 403d until the server was restarted.
dev: $(DEV_CONFIG) $(DEV_VAULT)
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) dev-api & \
	$(MAKE) dev-ui & \
	wait

dev-api: $(DEV_CONFIG) $(DEV_VAULT)
	uv run uvicorn loci.http_server:app --reload --port 8765

dev-ui: $(DEV_CONFIG) $(DEV_VAULT)
	cd app && npm run dev

# ---------------------------------------------------------------------------
# `make run` — the app against the vault you actually keep notes in.
#
# The inverse of `make dev`: no LOCI_CONFIG or LOCI_VAULT_ROOT override, so both
# halves read ~/.config/loci/config.yml — the same file ./run_server.sh and an
# installed MCP server use. The UI is the built bundle served on :4173 (already
# in the API's DEFAULT_ALLOWED_ORIGINS) rather than the dev server, so this runs
# the app as it ships instead of a development build of it.
# ---------------------------------------------------------------------------

# Resolved the way config_path() in src/loci/tools/vault_init.py does, so the
# preflight below reads the file the servers will actually open. A variable so
# the tests can point it at a scratch config.
RUN_CONFIG ?= $(if $(LOCI_CONFIG),$(LOCI_CONFIG),$(if $(XDG_CONFIG_HOME),$(XDG_CONFIG_HOME),$(HOME)/.config)/loci/config.yml)

# npm ci wipes and reinstalls, which is too slow to pay on every run. Gate it on
# the lockfile instead; `make test` still reinstalls unconditionally, where the
# guarantee matters more than the seconds.
#
# The target is a stamp file inside the directory, not the directory itself: npm
# ci deletes node_modules before installing, so an install that dies partway
# (network, EACCES) leaves a directory newer than the lockfile and make would
# treat the tree as built from then on. The stamp goes with the deletion and is
# written last, so a failed install just reinstalls on the next run.
NODE_MODULES := app/node_modules/.loci-installed
$(NODE_MODULES): app/package-lock.json
	npm ci --prefix app
	@touch $@

# Fail before the servers start rather than after — scripts/run_preflight.py
# says what it catches, and why it reads the config with the same YAML parser
# the servers use rather than pulling the line apart with sed.
#
# RUN_CHECKED is passed to the two sub-makes `run` forks. They each depend on
# the preflight so that starting one alone still checks, but the parent has run
# it already and three "serving ..." lines before anything starts are noise.
run-check:
	@$(if $(RUN_CHECKED),true,uv run python $(CURDIR)/scripts/run_preflight.py "$(RUN_CONFIG)")

# Each half brings the group down when it exits, so one dying stops the other
# instead of leaving a bare `wait` blocked on the survivor. uvicorn exits at
# once when :8765 is already taken (a stray make dev, an MCP server) and the UI
# would then come up proxying to nothing — the blank screen with no explanation
# that the preflight above exists to prevent. The error itself is already on
# screen by then; these lines only say why the other half went away.
run: run-check
	@trap 'kill 0' EXIT INT TERM; \
	{ $(MAKE) run-api RUN_CHECKED=1; \
	  echo "run-api stopped — stopping run-ui too." >&2; kill 0; } & \
	{ $(MAKE) run-ui RUN_CHECKED=1; \
	  echo "run-ui stopped — stopping run-api too." >&2; kill 0; } & \
	wait

run-api: run-check
	uv run uvicorn loci.http_server:app --port 8765

# Builds first: vite preview serves app/dist, and a stale bundle left by an
# older checkout is worse than the few seconds the build costs.
run-ui: run-check $(NODE_MODULES)
	cd app && npm run build && npm run preview

# ---------------------------------------------------------------------------
# Skills and releases
# ---------------------------------------------------------------------------

# Install the skill stubs into ~/.claude/skills/. Each stub calls read_skill,
# and the MCP server reads src/loci/skills/<name>/SKILL.md on every call, so
# editing a skill is live with nothing to re-run. The stubs only change when a
# skill is added, removed, or its trigger description reworded — and the
# post-checkout and post-merge hooks run this for you when a pull or a branch
# switch touches the skills tree. Same code path an installed wheel runs.
skills:
	uv run loci skills

# Build the distributable wheel — with the UI inside it.
#
# `uv build` alone ships a backend: the frontend lives in app/, which is not
# packaged, and an installed Loci has neither app/ nor Node to build it with.
# So the bundle is compiled into src/loci/static/ first, where pyproject's
# hatch `artifacts` entry picks it up.
#
# The bundle is rebuilt every time rather than reusing app/dist. A stale dist
# from an old checkout would ship silently, and a released UI that quietly
# lags the backend is worse than the minute the build costs.
#
# LOCI_CONFIG points at nothing on purpose. vite.config.js reads the API token
# out of config.yml and inlines it into the bundle, which is right for `make
# dev` and catastrophic here: on any machine that has ever started Loci, the
# builder's live token would be baked into a wheel and handed to whoever
# installs it. An empty LOCI_API_TOKEN does not do it — readApiToken() tests
# truthiness and falls through to the file. The served page gets its token from
# the meta tag http_server stamps into index.html, so nothing needs one baked in.
wheel: $(NODE_MODULES)
	cd app && LOCI_CONFIG=/nonexistent npm run build
	rm -rf src/loci/static
	cp -R app/dist src/loci/static
	rm -rf dist
	uv build
	@files=$$(unzip -l dist/*.whl | grep -c "loci/static/" || true); \
	  if [ "$$files" -eq 0 ]; then \
	    echo "wheel: no loci/static/ files in the wheel — the bundle was dropped." >&2; \
	    echo "Check [tool.hatch.build] artifacts in pyproject.toml." >&2; \
	    exit 1; \
	  fi; \
	  echo; \
	  echo "Built dist/ — the UI is inside:"; \
	  echo "  $$files frontend files packaged"

# A whole release: bump the version, open the PR, wait for its checks, merge
# it, tag main and push the tag. main is still never written to directly —
# the version change lands as a PR like anything else, and the merge waits on
# CI. Expect it to block for as long as the e2e suite runs.
#
# BUMP is required — there is no default, because guessing whether a release
# is a patch or a minor is exactly the judgement this leaves to you.
BUMP ?=
release:
	@test -n "$(BUMP)" || { echo "usage: make release BUMP=patch|minor|major" >&2; exit 1; }
	uv run python scripts/release.py release $(BUMP)

# The same thing in halves, for when CI wants watching by hand or a one-step
# run died partway: open the PR, then tag the merged result.
release-bump:
	@test -n "$(BUMP)" || { echo "usage: make release-bump BUMP=patch|minor|major" >&2; exit 1; }
	uv run python scripts/release.py bump $(BUMP)

# The tag is what .github/workflows/release.yml fires on.
release-publish:
	uv run python scripts/release.py publish
