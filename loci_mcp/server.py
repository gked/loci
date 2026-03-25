"""
loci_mcp/server.py
Loci MCP server for Claude Desktop — stdio transport.

Thin wrapper over api.py. All vault logic lives there.

Requirements:
  pip install "mcp[cli]" pyyaml

Registration (~/Library/Application Support/Claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "loci": {
        "command": "python",
        "args": ["/absolute/path/to/loci/loci_mcp/server.py"]
      }
    }
  }

Restart Claude Desktop after editing the config.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import api as loci
import nx_graph as graph
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("loci")


@mcp.tool()
def generate_uid() -> str:
    """Generate a random 8-character hex UID for a new vault item."""
    return loci.generate_uid()


@mcp.tool()
def check_duplicate(type: str, title: str, url: str = None) -> dict:
    """
    Check whether a similar vault item already exists before writing.
    Returns {"duplicate": false} or {"duplicate": true, "path": "...", "name": "..."}.
    Call this before write_vault when the user might be saving something they've saved before.
    """
    return loci.check_duplicate(type, title, url)


@mcp.tool()
def write_vault(
    type: str,
    title: str,
    body: str,
    tags: list[str] = None,
    domains: list[str] = None,
    summary: str = None,
    author: str = "self",
    relations: list[dict] = None,
    references: list[dict] = None,
    extra_fields: dict = None,
) -> dict:
    """
    Write a new item to the Loci vault. Returns {uid, path, type, title}.

    Run check_duplicate first unless the user has already confirmed they want to save.

    Args:
        type: note | article | conversation | project | task | event | entity | procedure | topic | reference
        title: Concise descriptive title
        body: Main content body (markdown)
        tags: 3-6 freeform lowercase hyphenated tags
        domains: One or more from: technology-engineering, science-research, business-strategy,
                 finance-economics, health-biology, philosophy-ethics, creativity-design,
                 personal-development, current-events-society
        summary: One-paragraph summary — what this is, why it matters, key insight
        author: "self" for user-produced content; entity name/UID for external
        relations: List of {uid: str, type: str} dicts
        references: List of {url: str, title: str, source_type: str} dicts
        extra_fields: Type-specific frontmatter fields
    """
    return loci.save(
        type=type, title=title, body=body, tags=tags, domains=domains,
        summary=summary, author=author, relations=relations,
        references=references, extra_fields=extra_fields,
    )


@mcp.tool()
def delete_vault(path: str) -> dict:
    """
    Delete a vault item permanently.

    Args:
        path: Absolute path or path relative to vault_root (e.g. "notes/my-note.md")

    Always confirm with the user before calling this. Deletion is irreversible.
    """
    try:
        return loci.delete(path)
    except FileNotFoundError as e:
        return {"error": str(e)}


@mcp.tool()
def patch_vault(path: str, updates: dict, body: str = None) -> dict:
    """
    Patch frontmatter fields on an existing vault item. updated_at is always bumped.

    Use this to correct or extend an existing item — e.g. add/remove relations,
    update tags, change status — without rewriting the whole file.

    Workflow:
      1. Call read_vault(path) to get the current content.
      2. Parse the fields you want to change and construct their new values in full
         (e.g. the complete new relations list, not just the items to add).
      3. Call patch_vault(path, updates={...}) with only the fields that changed.

    Args:
        path: Absolute path or path relative to vault_root (e.g. "notes/my-note.md")
        updates: Dict of frontmatter fields to overwrite. Pass complete new values.
                 Common uses:
                   relations: [{uid: "a1b2c3d4", type: "belongs-to"}, ...]
                   tags: ["tag-a", "tag-b"]
                   status: "done"
                   summary: "Updated summary."
        body: If provided, replaces the full body text.
    """
    try:
        return loci.patch(path, updates, body)
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}


@mcp.tool()
def read_vault(path: str) -> str:
    """
    Read a vault file. Accepts an absolute path or a path relative to vault_root.
    Examples: "notes/my-note.md"  or  "/Users/me/Nextcloud/loci/notes/..."
    """
    try:
        return loci.get(path)
    except FileNotFoundError as e:
        return str(e)


@mcp.tool()
def list_vault(type: str = None) -> dict:
    """
    List items in a vault type folder. Omit type to list all folders.
    Returns {type_name: [filename, ...], ...}.
    """
    return loci.list_items(type)


@mcp.tool()
def read_meta(file: str) -> str:
    """
    Read a vault meta file.
    file: type-dictionary | tag-dictionary | field-dictionary | foreign-definitions | config
    """
    try:
        return loci.read_meta(file)
    except (ValueError, FileNotFoundError) as e:
        return str(e)


@mcp.tool()
def fetch_url_metadata(url: str) -> dict:
    """
    Lightly fetch a URL and extract title, site name, and description.
    Use this for bookmark saves — does not return full page content.
    If the user wants full content extracted, use the article type instead.
    """
    return loci.fetch_url_metadata(url)


@mcp.tool()
def read_skill() -> str:
    """Read the current Loci skill instructions (skill/SKILL.md)."""
    try:
        return loci.read_skill()
    except FileNotFoundError as e:
        return str(e)


@mcp.tool()
def write_skill(content: str) -> str:
    """
    Overwrite the Loci skill instructions (skill/SKILL.md).
    Claude Code picks up the update automatically via the symlink.
    Claude Desktop users will need to re-paste into Project custom instructions.
    """
    try:
        return loci.write_skill(content)
    except FileNotFoundError as e:
        return str(e)


@mcp.tool()
def write_meta(file: str, content: str) -> str:
    """
    Overwrite a vault meta file.
    file: tag-dictionary | foreign-definitions
    """
    try:
        return loci.write_meta(file, content)
    except ValueError as e:
        return str(e)


@mcp.tool()
def query_related(uid: str, depth: int = 2) -> list[dict]:
    """
    Return all vault nodes within `depth` hops of the given uid.
    Results include distance from the origin node, sorted nearest-first.
    Each entry: {uid, title, type, distance}.
    """
    graph.get(loci._vault_root())
    return graph.related(uid, depth)


@mcp.tool()
def query_path(uid_from: str, uid_to: str) -> list[dict]:
    """
    Return the shortest path between two vault nodes as an ordered list.
    Each entry: {uid, title, type}.
    Returns an empty list if no path exists.
    """
    graph.get(loci._vault_root())
    return graph.path(uid_from, uid_to)


@mcp.tool()
def find_nodes(type: str = None, tag: str = None) -> list[dict]:
    """
    Find vault nodes by type and/or tag.
    At least one filter should be provided.
    Each entry: {uid, title, type, path}.
    """
    graph.get(loci._vault_root())
    return graph.find(type=type, tag=tag)


if __name__ == "__main__":
    transport = os.environ.get("LOCI_TRANSPORT", "stdio")
    if transport == "sse":
        import uvicorn
        uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=8000)
    else:
        mcp.run(transport=transport)
