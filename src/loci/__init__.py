"""
Loci — a personal knowledge vault served over MCP and HTTP.

Two console scripts ship from this package, deliberately as separate processes:

  loci-mcp  (loci.mcp_server:main)   stdio MCP server, spawned and killed by the
                                     MCP client — one per connected client.
  loci      (loci.http_server:main)  the web app, started by the user and
                                     outliving any client. This is the one a
                                     person types; loci-mcp is spawned for them.

Folding them into one process would let Claude Desktop's quit take the web app
down with it, and would start a web server per connected client.
"""
