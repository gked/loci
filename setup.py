"""
setup.py
One-time setup for Loci. Safe to re-run — all steps are idempotent.

What this does:
  1. Installs dependencies via uv
  2. Initializes the vault structure
  3. Registers the Loci MCP server in Claude Code  (~/.claude.json, user scope via `claude mcp add`)
  4. Registers the Loci MCP server in Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json)
  5. Creates symlink ~/.claude/skills/loci-save/ → skill/

Usage:
  python setup.py
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# Install dependencies before any local imports that require them
subprocess.run(["uv", "sync"], cwd=Path(__file__).parent, check=True)

# Add tools/ to path
sys.path.insert(0, str(Path(__file__).parent / "tools"))
from vault_init import init as vault_init

PROJECT_ROOT  = Path(__file__).parent.resolve()
MCP_SERVER    = PROJECT_ROOT / "loci_mcp" / "server.py"
SKILL_DIR     = PROJECT_ROOT / "loci-skill" / "loci-save"

CLAUDE_DESKTOP_CONFIG  = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
SKILLS_LINK            = Path.home() / ".claude" / "skills" / "loci-save"


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def register_mcp_claude_code() -> None:
    """Register loci MCP server with Claude Code using `claude mcp add --scope user`.

    Claude Code reads MCP servers from ~/.claude.json (not ~/.claude/settings.json).
    The only reliable way to register is via the CLI with --scope user so it is
    available across all projects.
    """
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    claude = shutil.which("claude")
    if not claude:
        print("  Warning: `claude` CLI not found — skipping Claude Code registration.")
        print("  Run manually: claude mcp add --scope user loci <uv-path> -- run --directory <project> python loci_mcp/server.py")
        return

    result = subprocess.run(
        [
            claude, "mcp", "add", "--scope", "user",
            "loci", uv,
            "--", "run", "--directory", str(PROJECT_ROOT), "python", "loci_mcp/server.py",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"  Registered via `claude mcp add --scope user` (~/.claude.json)")
    else:
        print(f"  Warning: registration failed — {result.stderr.strip()}")


def register_mcp_desktop(config_path: Path) -> None:
    """Add or update the loci MCP server entry in claude_desktop_config.json."""
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            print(f"  Warning: {config_path} is not valid JSON — skipping Claude Desktop.")
            return

    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    config.setdefault("mcpServers", {})
    config["mcpServers"]["loci"] = {
        "command": uv,
        "args": ["run", "--directory", str(PROJECT_ROOT), "python", "loci_mcp/server.py"],
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    print(f"  Registered: {config_path}")


def install_skill_symlink() -> None:
    """Create ~/.claude/skills/loci-save/ as a symlink to skill/."""
    SKILLS_LINK.parent.mkdir(parents=True, exist_ok=True)

    if SKILLS_LINK.is_symlink():
        SKILLS_LINK.unlink()
        print(f"  Replaced existing symlink.")
    elif SKILLS_LINK.exists():
        shutil.rmtree(SKILLS_LINK)
        print(f"  Replaced existing skill copy.")

    SKILLS_LINK.symlink_to(SKILL_DIR)
    print(f"  {SKILLS_LINK} → {SKILL_DIR}")


def print_desktop_fallback() -> None:
    """Print skill contents for manual paste into Claude Desktop Project."""
    skill_md = SKILL_DIR / "SKILL.md"
    print()
    print("=" * 60)
    print("Claude Desktop — if the skill does not auto-load")
    print("=" * 60)
    print("Paste the following into your Project's custom instructions:")
    print()
    print(skill_md.read_text() if skill_md.exists() else f"Skill file not found: {skill_md}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("\nLoci Setup\n")

    print("Step 1 — Vault init")
    vault_init()
    print()

    print("Step 2 — Claude Code MCP registration")
    register_mcp_claude_code()
    print()

    print("Step 3 — Claude Desktop MCP registration")
    register_mcp_desktop(CLAUDE_DESKTOP_CONFIG)
    print()

    print("Step 4 — Skill symlink")
    install_skill_symlink()
    print()

    print("Done.")
    print()
    print("Next steps:")
    print("  1. Restart Claude Code")
    print("  2. Restart Claude Desktop")

    print_desktop_fallback()


if __name__ == "__main__":
    main()
