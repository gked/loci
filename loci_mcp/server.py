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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import api as loci
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
    date: str = None,
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
        date: Override date YYYY-MM-DD (default: today)
    """
    return loci.save(
        type=type, title=title, body=body, tags=tags, domains=domains,
        summary=summary, author=author, relations=relations,
        references=references, extra_fields=extra_fields, date=date,
    )


@mcp.tool()
def read_vault(path: str) -> str:
    """
    Read a vault file. Accepts an absolute path or a path relative to vault_root.
    Examples: "notes/2026-03-21-my-note.md"  or  "/Users/me/Nextcloud/loci/notes/..."
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
    file: type-dictionary | tag-dictionary | foreign-definitions | config
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


if __name__ == "__main__":
    mcp.run()
