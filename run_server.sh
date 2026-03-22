#!/bin/sh
# Loci MCP server launcher — uses the project venv.
# Run `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` to set up.
cd "$(dirname "$0")"
exec .venv/bin/python3 loci_mcp/server.py
