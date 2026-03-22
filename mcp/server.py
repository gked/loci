"""
mcp/server.py
Loci MCP server — exposes vault tools to Claude.ai via the MCP protocol.

Status: Placeholder — implement when WebDAV credentials and MCP setup are ready.

This server wraps the tools/ implementations and exposes them as MCP tools:
- write_vault: write an item to the vault via WebDAV
- read_vault: read a file from the vault via WebDAV
- generate_uid: generate a UID (since Claude.ai can't run Python directly)
- list_vault: list items in a type folder

Dependencies:
- mcp (pip install mcp)
- httpx (for WebDAV requests)
- pyyaml

Configuration:
- Reads vault_root and webdav_url from ~/.loci/config.yml
"""

# TODO: implement when MCP layer is ready
# Reference: https://github.com/anthropics/mcp

raise NotImplementedError(
    "MCP server not yet implemented. "
    "Use tools/ directly via Claude Code for now."
)
