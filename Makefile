.PHONY: test test-cov cov-html

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
