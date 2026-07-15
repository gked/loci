.PHONY: test test-cov cov-html dev dev-api dev-ui

test:
	uv sync --extra dev
	uv run pytest server/tests/ -v

test-cov:
	uv sync --extra dev
	uv run pytest server/tests/ --cov=tools --cov=api --cov=loci_mcp --cov-report=term-missing

cov-html:
	uv sync --extra dev
	uv run pytest server/tests/ --cov=tools --cov=api --cov=loci_mcp --cov-report=html:htmlcov
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
