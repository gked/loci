#!/bin/sh
# Loci MCP server launcher — uses uv to manage the project venv.
# Run `uv sync` to set up dependencies.
cd "$(dirname "$0")"
exec uv run python server/loci_mcp/server.py
