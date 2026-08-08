.PHONY: test test-fast test-e2e test-cov cov-html e2e-install dev dev-api dev-ui hooks screenshots

# One-time per clone: point git at the versioned hooks in .githooks/.
# They block commits, merges, and pushes that land directly on main.
hooks:
	git config core.hooksPath .githooks
	@echo "hooks installed (core.hooksPath = .githooks)"

# Full suite — Python unit tests + browser e2e. Needs `make e2e-install` once.
test:
	uv sync --extra dev
	npm ci --prefix app
	uv run pytest server/tests/ -v

# Everything except the browser suite. No Node or Playwright browser required.
test-fast:
	uv sync --extra dev
	uv run pytest server/tests/ -v -m "not e2e"

# Browser suite only.
test-e2e:
	uv sync --extra dev
	npm ci --prefix app
	uv run pytest server/tests/e2e/ -v

# One-time (and after Playwright upgrades): download the browser binary.
e2e-install:
	uv sync --extra dev
	uv run playwright install chromium

# Recapture the README screenshots from the e2e fixture vault into docs/images/.
# Opt-in: these specs skip during a normal run. Commit the images afterwards.
screenshots:
	uv sync --extra dev
	npm ci --prefix app
	LOCI_CAPTURE_SCREENSHOTS=1 uv run --with pillow pytest server/tests/e2e/test_screenshots.py -v -s

test-cov:
	uv sync --extra dev
	uv run pytest server/tests/ --cov=tools --cov=api --cov=loci_mcp --cov-report=term-missing -m "not e2e"

cov-html:
	uv sync --extra dev
	uv run pytest server/tests/ --cov=tools --cov=api --cov=loci_mcp --cov-report=html:htmlcov -m "not e2e"
	open htmlcov/index.html

dev:
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) dev-api & \
	$(MAKE) dev-ui & \
	wait

dev-api:
	uv run uvicorn server.http_server:app --reload --port 8765

dev-ui:
	cd app && npm run dev
