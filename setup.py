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
# Every packaged skill, not a hand-kept subset — a hardcoded list is how
# loci-inbox and loci-ingest-directory ended up installed by neither setup
# script and documented as a manual `ln -s` loop in the README instead.
# Scanned rather than imported from loci.skills_install: this module has to
# stay importable before `uv sync` has installed the package.
SKILLS        = sorted(
    d.name for d in SKILLS_DIR.iterdir()
    if d.is_dir() and (d / "SKILL.md").is_file()
) if SKILLS_DIR.is_dir() else []

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
    """Point ~/.claude/skills/<skill>/ at each packaged skill.

    Delegates to loci.skills_install so the checkout path and the installed
    path share one implementation and cannot drift. link=True because this
    script only ever runs from a checkout, where editing a skill and seeing it
    live is the point; `loci skills` copies instead, since a link into an
    installed wheel dangles the moment it is upgraded. force=True keeps the old
    behaviour of relinking unconditionally.

    Imported inside the function, not at module scope: the package only becomes
    importable once sync_and_init_vault() has run `uv sync`.
    """
    from loci import skills_install

    statuses = skills_install.plan(
        skills_root=Path.home() / ".claude" / "skills",
        source=SKILLS_DIR,
        force=True,
    )
    if not statuses:
        # Nothing packaged means nothing to link. Saying so beats silence: the
        # alternative once was unlinking a working skill and pointing it at a
        # directory that did not exist.
        print(f"  Skipped: no skills found in {SKILLS_DIR}")
        return

    for status in skills_install.apply(statuses, link=True):
        if status.action == skills_install.REMOVE:
            print(f"  {status.dest} (removed — no longer shipped)")
        else:
            print(f"  {status.dest} → {status.source}")


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
