"""
setup.py
One-time setup for Loci. Safe to re-run — all steps are idempotent.

What this does:
  1. Installs dependencies via uv
  2. Initializes the vault structure
  3. Registers the Loci MCP server in Claude Code  (~/.claude.json, user scope via `claude mcp add`)
  4. Registers the Loci MCP server in Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json)
  5. Creates symlink ~/.claude/skills/<skill>/ → src/loci/skills/<skill>/

Usage (from the loci checkout):
  uv run setup.py
"""

import json
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT  = Path(__file__).parent.resolve()
SKILLS_DIR    = PROJECT_ROOT / "src" / "loci" / "skills"
SKILLS        = ["loci-save", "loci-query"]

CLAUDE_DESKTOP_CONFIG  = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


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
        print("  Run manually: claude mcp add --scope user loci <uv-path> -- run --directory <project> loci-mcp")
        return

    result = subprocess.run(
        [
            claude, "mcp", "add", "--scope", "user",
            "loci", uv,
            "--", "run", "--directory", str(PROJECT_ROOT), "loci-mcp",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"  Registered via `claude mcp add --scope user` (~/.claude.json)")
    else:
        print(f"  Warning: registration failed — {result.stderr.strip()}")


def register_mcp_claude_desktop(config_path: Path) -> None:
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
        "args": ["run", "--directory", str(PROJECT_ROOT), "loci-mcp"],
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    print(f"  Registered: {config_path}")


def install_skill_symlink() -> None:
    """Create ~/.claude/skills/<skill>/ symlinks for each skill."""
    skills_root = Path.home() / ".claude" / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    for skill_name in SKILLS:
        src = SKILLS_DIR / skill_name
        dst = skills_root / skill_name

        if not src.is_dir():
            # Unlinking dst and then pointing it at a path that does not exist
            # replaces a working skill install with a dangling symlink — and one
            # of these skills is how the user was told to run this script.
            print(f"  Skipped {skill_name}: {src} does not exist")
            continue

        if dst.is_symlink():
            dst.unlink()
            print(f"  Replaced existing symlink: {skill_name}")
        elif dst.exists():
            shutil.rmtree(dst)
            print(f"  Replaced existing skill copy: {skill_name}")

        dst.symlink_to(src)
        print(f"  {dst} → {src}")


def print_desktop_fallback() -> None:
    """Print skill contents for manual paste into Claude Desktop Project."""
    print()
    print("=" * 60)
    print("Claude Desktop — if the skills do not auto-load")
    print("=" * 60)
    print("Paste the following into your Project's custom instructions:")
    for skill_name in SKILLS:
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        print(f"\n--- {skill_name} ---\n")
        print(skill_md.read_text() if skill_md.exists() else f"Skill file not found: {skill_md}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def sync_and_init_vault() -> None:
    """Install dependencies, then seed the vault.

    Both live here rather than at module scope so the module can be imported
    without running `uv sync` — that is what lets the tests exercise the skill
    installer. vault_init is imported inside the function for the same reason:
    it only becomes importable once `uv sync` has installed the project.
    """
    subprocess.run(["uv", "sync"], cwd=PROJECT_ROOT, check=True)
    from loci.tools.vault_init import init as vault_init
    vault_init()


def main() -> None:
    print("\nLoci Setup\n")

    print("Step 1 — Dependencies and vault init")
    sync_and_init_vault()
    print()

    print("Step 2 — Claude Code MCP registration")
    register_mcp_claude_code()
    print()

    print("Step 3 — Claude Desktop MCP registration")
    register_mcp_claude_desktop(CLAUDE_DESKTOP_CONFIG)
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
