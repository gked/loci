.PHONY: test test-cov

test:
	uv sync --extra dev
	uv run pytest tests/ -v

test-cov:
	uv sync --extra dev
	uv run pytest tests/ --cov=tools --cov=api --cov-report=term-missing
