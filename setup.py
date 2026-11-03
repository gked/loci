"""
setup.py
One-time setup for Loci. Safe to re-run — all steps are idempotent.

What this does:
  1. Installs dependencies via uv
  2. Initializes the vault structure
  3. Registers the Loci MCP server in Claude Code  (~/.claude.json, user scope via `claude mcp add`)
  4. Registers the Loci MCP server in Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json)
  5. Installs the skill stubs into ~/.claude/skills/<skill>/
  6. If the `codex` CLI is installed: registers the MCP server with Codex
     (`codex mcp add`) and installs the stubs into $CODEX_HOME/skills/
     (default ~/.codex/skills/). Skipped, with the manual command, otherwise.

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


def register_mcp_codex() -> bool:
    """Register loci MCP server with Codex using `codex mcp add`.

    Returns True when Codex is installed and the registration succeeded, so the
    caller installs Codex's skill stubs only for an agent that is really there.
    """
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    codex = shutil.which("codex")
    if not codex:
        print("  Skipped: `codex` CLI not found.")
        print("  To add Codex later: codex mcp add loci -- <uv-path> run --directory <project> loci-mcp")
        print("                      uv run loci skills --agent codex")
        return False

    result = subprocess.run(
        [
            codex, "mcp", "add", "loci",
            "--", uv, "run", "--directory", str(PROJECT_ROOT), "loci-mcp",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("  Registered via `codex mcp add`")
        return True
    print(f"  Warning: registration failed — {result.stderr.strip()}")
    return False


def install_skill_stubs(skills_root: Path | None = None) -> None:
    """Install a stub for each packaged skill into ~/.claude/skills/, or into
    `skills_root` for another agent.

    Delegates to loci.skills_install so the checkout path and the installed
    path share one implementation and cannot drift. Stubs, not symlinks, from
    a checkout too: the stub calls read_skill, and the MCP server reads the
    checkout's SKILL.md on every call, so an edit to a skill is live without
    any link. A symlink would hand Claude Code the procedure directly and
    skip the user's overlay — see skills_install.py.

    Imported inside the function, not at module scope: the package only becomes
    importable once sync_and_init_vault() has run `uv sync`.
    """
    from loci import skills_install

    if skills_root is None:
        skills_root = Path.home() / ".claude" / "skills"
    statuses = skills_install.plan(
        skills_root=skills_root,
        source=SKILLS_DIR,
    )
    if not statuses:
        # Nothing packaged means nothing to install. Saying so beats silence:
        # the alternative once was unlinking a working skill and pointing it
        # at a directory that did not exist.
        print(f"  Skipped: no skills found in {SKILLS_DIR}")
        return

    for status in skills_install.apply(statuses):
        print(f"  {status.action}: {status.dest}")
    if not any(s.writes for s in statuses):
        print("  Up to date.")


def print_desktop_fallback() -> None:
    """Print the skill stubs for manual paste into a Claude Desktop Project.

    The stubs, not the procedures: the procedure is served by the MCP server
    with the user's additions appended, and a pasted copy of it would run on
    its own and never see them. The stub is short and never changes, so this
    is a one-time paste.
    """
    from loci import skills_install

    print()
    print("=" * 60)
    print("Claude Desktop — if the skills do not auto-load")
    print("=" * 60)
    print("Paste the following into your Project's custom instructions:")
    for skill_name in SKILLS:
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        print(f"\n--- {skill_name} ---\n")
        if skill_md.exists():
            print(skills_install.stub(skill_name, skill_md.read_text()))
        else:
            print(f"Skill file not found: {skill_md}")
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

    print("Step 4 — Skill stubs")
    install_skill_stubs()
    print()

    print("Step 5 — Codex (optional)")
    codex_ready = register_mcp_codex()
    if codex_ready:
        from loci import skills_install
        install_skill_stubs(skills_install.agent_skills_root("codex"))
    print()

    print("Done.")
    print()
    print("Next steps:")
    print("  1. Restart Claude Code")
    print("  2. Restart Claude Desktop")
    if codex_ready:
        print("  3. Restart Codex")

    print_desktop_fallback()


if __name__ == "__main__":
    main()
