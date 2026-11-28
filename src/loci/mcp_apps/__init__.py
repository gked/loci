"""
MCP Apps views: interactive HTML that a host renders under a tool call.

A view is one self-contained HTML file served as a `ui://` resource. It must
live inside this package — only `src/loci/` reaches the wheel — and it must
make no network request: the host's default CSP is `connect-src 'none'`, so a
view that fetches anything is broken in Claude Desktop however it looks in a
browser. Everything the view needs arrives through the host (tool results,
`tools/call`), which is also what keeps it working with the separate MCP
process rather than the web server.
"""
from pathlib import Path

NODE_VIEW_URI = "ui://loci/node-view.html"
UI_MIME = "text/html;profile=mcp-app"
UI_EXTENSION = "io.modelcontextprotocol/ui"

_NODE_VIEW = Path(__file__).with_name("node_view.html")


def node_view_html() -> str:
    """The node view, read on every call, so an edit shows without restarting the server."""
    return _NODE_VIEW.read_text(encoding="utf-8")
