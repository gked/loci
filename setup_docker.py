"""
setup_docker.py
Interactive Docker setup for Loci.

Run it with `uv run setup_docker.py`, as docs/setup.md says. Step 6 installs the
skills through loci.skills_install rather than a hand-rolled copy of it, so
this script is no longer standalone: it needs the project's environment.
require_loci_package() checks that up front instead of letting the import fail
at step 6, with Docker installed, the vault configured and the container
already running.

Walks through:
  1. Checking / installing Docker or OrbStack
  2. Vault path
  3. rclone sync config (optional)
  4. Building and starting the container
  5. Verifying the server is up
  6. Installing the Loci skill stubs in Claude Code
  7. Registering the local stdio MCP server with Claude Code and Claude Desktop
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
COMPOSE_FILE = PROJECT_ROOT / "deploy" / "docker-compose.yml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ask(prompt: str, default: str = "") -> str:
    display = f"{prompt} (default: {default}): " if default else f"{prompt}: "
    value = input(display).strip()
    return value if value else default


def confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() == "y"


def run(cmd: list, env: dict = None, check: bool = True) -> subprocess.CompletedProcess:
    import os
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(cmd, env=full_env, check=check)


def docker_running() -> bool:
    result = subprocess.run(
        ["docker", "info"], capture_output=True
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Step 1 — Docker / OrbStack
# ---------------------------------------------------------------------------

def ensure_docker() -> None:
    print("\nStep 1 — Docker")

    has_docker = shutil.which("docker") is not None
    has_orbstack = Path("/Applications/OrbStack.app").exists()
    has_dockerdesktop = Path("/Applications/Docker.app").exists()

    if has_docker and docker_running():
        print("  Docker is installed and running.")
        return

    if has_docker and not docker_running():
        print("  Docker is installed but not running.")
        if has_orbstack:
            print("  Starting OrbStack...")
            subprocess.run(["open", "-a", "OrbStack"], check=False)
        elif has_dockerdesktop:
            print("  Starting Docker Desktop...")
            subprocess.run(["open", "-a", "Docker"], check=False)
        print("  Waiting for Docker to start", end="", flush=True)
        for _ in range(30):
            time.sleep(2)
            print(".", end="", flush=True)
            if docker_running():
                print(" ready.")
                return
        print()
        print("  Docker did not start in time. Please start it manually and re-run.")
        sys.exit(1)

    # Docker not installed
    has_brew = shutil.which("brew") is not None
    print("  Docker is not installed.")

    if not has_brew:
        print("  Homebrew is not installed. Install it from https://brew.sh, then re-run.")
        sys.exit(1)

    print()
    print("  Choose a Docker runtime:")
    print("  [1] OrbStack  — lightweight, fast, recommended for macOS")
    print("  [2] Docker Desktop — official Docker app")
    print("  [3] Skip — I'll install it myself")
    choice = input("  Enter 1, 2, or 3: ").strip()

    if choice == "1":
        print("  Installing OrbStack via Homebrew...")
        run(["brew", "install", "--cask", "orbstack"])
        print("  Launching OrbStack...")
        subprocess.run(["open", "-a", "OrbStack"], check=False)
    elif choice == "2":
        print("  Installing Docker Desktop via Homebrew...")
        run(["brew", "install", "--cask", "docker"])
        print("  Launching Docker Desktop...")
        subprocess.run(["open", "-a", "Docker"], check=False)
    else:
        print("  Install Docker or OrbStack, then re-run this script.")
        sys.exit(0)

    print("  Waiting for Docker to start", end="", flush=True)
    for _ in range(30):
        time.sleep(2)
        print(".", end="", flush=True)
        if docker_running():
            print(" ready.")
            return
    print()
    print("  Docker did not start in time. Please open it manually and re-run.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Step 2 — Vault path
# ---------------------------------------------------------------------------

def ask_vault_path() -> Path:
    """
    Ask for the vault location. No default — see prompt_vault_root() in
    src/loci/tools/vault_init.py, which this mirrors so the two wizards agree
    about what a vault path is. The path is bind-mounted into the container,
    so it belongs somewhere the user keeps, not somewhere in this checkout.
    """
    print("\nStep 2 — Vault location")
    print("  This directory is mounted into the container and holds your data,")
    print("  so it has to be a path you choose — there is no default.")
    while True:
        try:
            raw = input("  Where should the vault live? (absolute path, required): ").strip()
        except EOFError:
            print()
            sys.exit("  No vault path given. Re-run this script on a terminal.")
        if not raw:
            print("  A vault path is required — there is no default.")
            continue
        try:
            path = Path(raw).expanduser()
        except (RuntimeError, KeyError):
            # No such user, or no home directory to expand ~ against.
            print(f"  Could not work out what {raw} expands to. Start from / or ~/.")
            continue
        if not path.is_absolute():
            print(f"  {path} is not an absolute path. Start from / or ~.")
            continue
        path = path.resolve()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"  Cannot create {path}: {exc}")
            continue
        print(f"  Vault path: {path}")
        return path


# ---------------------------------------------------------------------------
# Step 3 — rclone sync
# ---------------------------------------------------------------------------

def ask_sync_config() -> dict:
    print("\nStep 3 — Sync (optional)")
    print("  rclone supports Nextcloud, Dropbox, Google Drive, OneDrive, S3, and more.")

    if not confirm("  Set up rclone sync?"):
        print("  Skipping sync — vault will be local only.")
        return {}

    rclone_conf_default = Path.home() / ".config" / "rclone" / "rclone.conf"
    if not rclone_conf_default.exists():
        print(f"  No rclone config found at {rclone_conf_default}.")
        sample = PROJECT_ROOT / "sync" / "rclone.conf.sample"
        if confirm(f"  Copy the sample config to {rclone_conf_default}?"):
            rclone_conf_default.parent.mkdir(parents=True, exist_ok=True)
            import shutil as sh
            sh.copy(sample, rclone_conf_default)
            print(f"  Copied. Edit {rclone_conf_default} with your credentials, then re-run.")
            sys.exit(0)
        else:
            print("  Skipping sync.")
            return {}

    rclone_conf = ask("  rclone config path", str(rclone_conf_default))
    remote = ask("  rclone remote name (e.g. nextcloud, dropbox)")
    remote_path = ask("  Path on the remote", "loci")
    interval = ask("  Sync interval in seconds", "300")

    return {
        "SYNC_REMOTE": remote,
        "SYNC_REMOTE_PATH": remote_path,
        "SYNC_INTERVAL": interval,
        "RCLONE_CONFIG": rclone_conf,
    }


# ---------------------------------------------------------------------------
# Step 4 — Build and start
# ---------------------------------------------------------------------------

def start_container(vault_path: Path, sync_env: dict) -> None:
    print("\nStep 4 — Build and start")

    env = {
        "VAULT_PATH": str(vault_path),
        **sync_env,
    }

    print("  Building image and starting container...")
    run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "--build"],
        env=env,
    )


# ---------------------------------------------------------------------------
# Step 5 — Verify
# ---------------------------------------------------------------------------

def verify() -> None:
    print("\nStep 5 — Verifying server")
    import urllib.request
    import urllib.error

    print("  Waiting for server", end="", flush=True)
    for _ in range(15):
        time.sleep(1)
        print(".", end="", flush=True)
        try:
            urllib.request.urlopen("http://localhost:4444/sse", timeout=2)
            print(" up.")
            return
        except Exception:
            pass
    print()
    print("  Server did not respond. Check logs with:")
    print(f"    docker compose -f {COMPOSE_FILE} logs")


# ---------------------------------------------------------------------------
# Step 6 — Install skill
# ---------------------------------------------------------------------------

def install_skill() -> None:
    """Install a stub for every packaged skill into ~/.claude/skills/.

    Shares one implementation with setup.py and `loci skills` via
    loci.skills_install. The hand-rolled loop this replaces installed two of
    the four skills, and its cleanup line (`rmtree if is_dir() else unlink`)
    raised NotADirectoryError on a re-run, because a symlink to a directory
    answers True to is_dir() and rmtree refuses to follow it.

    Stubs, not links, even from a checkout: the stub calls read_skill on the
    container's server, which is where the user's overlay is assembled in.
    """
    from loci import skills_install

    print("\nStep 6 — Loci skills")

    skills_source = PROJECT_ROOT / "src" / "loci" / "skills"
    statuses = skills_install.plan(
        skills_root=Path.home() / ".claude" / "skills",
        source=skills_source,
    )
    if not statuses:
        print(f"  Skill source not found at {skills_source} — skipping.")
        return

    for status in skills_install.apply(statuses):
        print(f"  {status.action}: {status.dest}")

    print("  Restart Claude Code to pick them up.")


# ---------------------------------------------------------------------------
# Step 7 — MCP registration
# ---------------------------------------------------------------------------

def register_mcp_claude_code() -> None:
    """Register loci stdio MCP server with Claude Code (user scope via `claude mcp add`)."""
    import json

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
        print("  Registered via `claude mcp add --scope user` (~/.claude.json)")
    else:
        print(f"  Warning: registration failed — {result.stderr.strip()}")


def register_mcp_desktop() -> None:
    """Add or update the loci MCP server entry in claude_desktop_config.json."""
    config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    import json

    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            print(f"  Warning: {config_path} is not valid JSON — skipping Claude Desktop.")
            return

    config.setdefault("mcpServers", {})
    config["mcpServers"]["loci"] = {
        "url": "http://localhost:4444/sse",
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    print(f"  Registered: {config_path}")


def register_mcp() -> None:
    print("\nStep 7 — MCP registration")
    register_mcp_claude_code()
    register_mcp_desktop()


# ---------------------------------------------------------------------------
# Step 8 — Next steps
# ---------------------------------------------------------------------------

def print_next_steps() -> None:
    print("\nDone. Next steps:\n")
    print("  1. Restart Claude Code to load the skill and MCP server.")
    print()
    print("  2. Open Claude Code and say:")
    print("       Save this as a note: Loci is now set up and working.")
    print()
    print("  3. For remote access (Claude.ai / mobile):")
    print("       Put the server behind nginx + Cloudflare Access.")
    print(f"       See deploy/nginx.conf.sample for the nginx config.")
    print()
    print("  Manage the container:")
    print()
    print("    Terminal:")
    print(f"      Restart:  docker compose -f {COMPOSE_FILE} restart")
    print(f"      Rebuild:  VAULT_PATH=<path> docker compose -f {COMPOSE_FILE} up -d --build")
    print(f"      Stop:     docker compose -f {COMPOSE_FILE} down")
    print(f"      Logs:     docker compose -f {COMPOSE_FILE} logs -f")
    print()
    print("    OrbStack:")
    print("      Open the OrbStack app — the 'loci' container appears in the sidebar.")
    print("      Restart, stop, or view logs with a single click.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def require_loci_package() -> None:
    """Stop before touching the machine if `loci` is not importable.

    `uv run setup_docker.py` syncs the project first, so this passes there.
    A bare `python3 setup_docker.py` used to get as far as step 6 before dying
    on the import — after Docker was installed, the vault configured and the
    container started.
    """
    try:
        import loci.skills_install  # noqa: F401
    except ImportError:
        print(
            "This script needs the loci package importable, and it is not.\n"
            "Run it through uv, which syncs the project first:\n"
            "    uv run setup_docker.py",
            file=sys.stderr,
        )
        raise SystemExit(1)


def main() -> None:
    print("\nLoci Docker Setup\n")

    require_loci_package()
    ensure_docker()
    vault_path = ask_vault_path()
    sync_env = ask_sync_config()
    start_container(vault_path, sync_env)
    verify()
    install_skill()
    register_mcp()
    print_next_steps()


if __name__ == "__main__":
    main()
