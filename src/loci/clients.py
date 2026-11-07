"""
The agents Loci can be wired into, and how to wire each one.

Two things differ per agent and nothing else: where its skills live, and how
its MCP server is registered. Everything downstream (the stub writer in
skills_install.py, `loci register`, setup.py) asks this module rather than
hardcoding `~/.claude`, so a new agent is one more entry here.

Detection never decides. `detected()` says which agents look installed; the
caller offers them, and `resolve_targets()` only picks one on its own when
there is no real choice to make (see its docstring).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Same marker skills_install uses to recognise stubs this installer wrote.
SKILL_NAME_PREFIX = "loci-"

# How long one `hermes` / `claude` subprocess may run. `hermes mcp add` tries
# to reach the server it is registering and then waits on prompts; without a
# bound a stalled one hangs `loci register` and setup.py for good.
SUBPROCESS_TIMEOUT = 60

# Two newlines: `hermes mcp add` asks "enable all tools?" and, when it cannot
# reach the server yet, "save anyway?". Both are yes for a fresh registration.
_HERMES_ANSWERS = "y\ny\n"


def packaged_skill_names() -> frozenset[str]:
    """Names of the skills this package ships (`skills/<name>/SKILL.md`).

    Read from the package tree so `Client.installed()` can tell Loci's stubs
    from a user's own `loci-*` skill. `references/` is not a skill.
    """
    root = Path(__file__).parent / "skills"
    if not root.is_dir():
        return frozenset()
    return frozenset(
        d.name for d in root.iterdir()
        if d.is_dir() and d.name != "references" and (d / "SKILL.md").is_file()
    )


def _hermes_home() -> Path:
    # Profiles move the whole tree, so HERMES_HOME wins over ~/.hermes.
    override = os.environ.get("HERMES_HOME", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".hermes"


@dataclass(frozen=True)
class Client:
    key: str
    label: str
    binary: str
    home: Callable[[], Path]
    skills_root: Callable[[], Path]
    # How the agent names a tool of the `loci` MCP server. Claude shows
    # `mcp__loci__x`; the procedures write the shorthand `loci__x`. Hermes
    # shows `mcp_loci_x`.
    read_skill_tool: str
    restart: str

    def detected(self) -> bool:
        return shutil.which(self.binary) is not None or self.home().is_dir()

    def installed(self) -> bool:
        """True when Loci stubs are already in this agent's skills directory.

        Matches the skills this package ships by name, not the `loci-` prefix:
        a user's own `loci-foo` skill must not enrol the agent in automatic
        refreshes. (Cleaning up a skill Loci once shipped is skills_install's
        job, once the agent is enrolled by any current stub.)
        """
        root = self.skills_root()
        if not root.is_dir():
            return False
        return any((root / name / "SKILL.md").is_file() for name in packaged_skill_names())


CLAUDE = Client(
    key="claude",
    label="Claude Code",
    binary="claude",
    home=lambda: Path.home() / ".claude",
    skills_root=lambda: Path.home() / ".claude" / "skills",
    read_skill_tool="loci__read_skill",
    restart="Claude Code / Claude Desktop",
)

HERMES = Client(
    key="hermes",
    label="Hermes",
    binary="hermes",
    home=_hermes_home,
    skills_root=lambda: _hermes_home() / "skills",
    read_skill_tool="mcp_loci_read_skill",
    restart="Hermes (or run /reload-mcp)",
)

CLIENTS = (CLAUDE, HERMES)


class TargetError(Exception):
    """The target could not be settled. The message says what to pass."""


def by_key(key: str) -> Client:
    for client in CLIENTS:
        if client.key == key:
            return client
    raise TargetError(f"Unknown target {key!r}. Choose from: {', '.join(c.key for c in CLIENTS)}, all.")


def detected() -> list[Client]:
    return [c for c in CLIENTS if c.detected()]


def installed() -> list[Client]:
    return [c for c in CLIENTS if c.installed()]


def _parse_spec(spec: str) -> list[Client]:
    keys = [k.strip().lower() for k in spec.split(",") if k.strip()]
    if "all" in keys:
        return list(CLIENTS)
    if not keys:
        raise TargetError("--target is empty.")
    # Order and duplicates follow CLIENTS, not the argument.
    wanted = {by_key(k).key for k in keys}
    return [c for c in CLIENTS if c.key in wanted]


def _ask_which(found: list[Client], stdin, out) -> list[Client]:
    """Checklist on a terminal. Agents that already have Loci start selected."""
    defaults = [i for i, c in enumerate(found, 1) if c.installed()]
    print("Several agents found. Install Loci for:", file=out)
    for i, c in enumerate(found, 1):
        note = "  (already has Loci)" if c.installed() else ""
        print(f"  {i}) {c.label}{note}", file=out)
    hint = ",".join(map(str, defaults)) if defaults else "none"
    print(f"Numbers, comma-separated, or 'all' [{hint}]: ", end="", file=out, flush=True)
    answer = stdin.readline().strip().lower()

    if not answer:
        chosen = [found[i - 1] for i in defaults]
    elif answer == "all":
        chosen = list(found)
    else:
        try:
            chosen = [found[int(n) - 1] for n in answer.replace(" ", "").split(",") if n]
        except (ValueError, IndexError):
            raise TargetError(f"Could not read {answer!r}. Pass --target to skip the prompt.")
    if not chosen:
        raise TargetError("Nothing selected.")
    return chosen


def resolve_targets(spec: str | None, stdin=None, out=None) -> list[Client]:
    """Settle which agents to act on.

    An explicit `spec` ("claude", "claude,hermes", "all") is taken as given.
    Without one: a single detected agent is used; several are put to the user
    on a terminal and refused otherwise, because "install everything I can
    find" is not a decision to make for someone. The exception is an agent that
    already has Loci stubs: refreshing those is an update, not an enrolment,
    so a non-interactive run does it without asking.
    """
    if spec:
        return _parse_spec(spec)

    already = installed()
    found = detected()
    interactive = stdin is not None and hasattr(stdin, "isatty") and stdin.isatty()

    if len(found) > 1 and interactive:
        return _ask_which(found, stdin, out)
    if already:
        return already
    if len(found) == 1:
        return found
    if not found:
        raise TargetError(
            "No supported agent found (looked for: "
            + ", ".join(f"{c.label} at {c.home()}" for c in CLIENTS)
            + "). Pass --target to install anyway."
        )
    raise TargetError(
        "Several agents found ("
        + ", ".join(c.label for c in found)
        + "). Pass --target claude, --target hermes or --target all."
    )


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------

TIMED_OUT = 124  # the shell convention for "killed by timeout"


def _run(cmd: list[str], stdin_text: str | None = None) -> subprocess.CompletedProcess:
    """Run a command with a bound on how long it may take.

    A timeout is reported as a failed result (returncode 124, a stderr that
    says so) rather than raised, so every caller already handles it as one
    more way for the command to fail.
    """
    try:
        return subprocess.run(
            cmd, input=stdin_text, capture_output=True, text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            cmd, TIMED_OUT, "", f"timed out after {SUBPROCESS_TIMEOUT}s"
        )


def _hermes_registered() -> bool:
    """True when Hermes has a non-empty `mcp_servers.loci` config entry.

    Reads the exit status and whether anything came back, not the text of the
    entry: `hermes config get` exits non-zero ("Config key not set") for a
    missing key, and which fields an entry prints (`command:`, `url:`, ...) is
    Hermes's to change.
    """
    binary = shutil.which("hermes")
    if not binary:
        return False
    result = _run([binary, "config", "get", "mcp_servers.loci"])
    out = result.stdout.strip()
    return result.returncode == 0 and bool(out) and "not set" not in out.lower()


def register_mcp(
    client: Client, command: str = "loci-mcp", args: list[str] | None = None
) -> tuple[bool, str]:
    """Register the Loci MCP server with one agent. Returns (ok, message).

    Re-running is safe: an existing `loci` entry is left alone. `command`/`args`
    default to the installed console script; setup.py passes `uv run
    --directory <checkout>` for a clone.
    """
    args = args or []
    binary = shutil.which(client.binary)
    if client.key == "hermes":
        manual = f"hermes mcp add loci --command {command}" + (f" --args {' '.join(args)}" if args else "")
    else:
        manual = f"claude mcp add --scope user loci {command}" + (f" -- {' '.join(args)}" if args else "")
    if not binary:
        return False, f"`{client.binary}` not found. Run it yourself: {manual}"

    if client.key == "claude":
        result = _run([binary, "mcp", "add", "--scope", "user", "loci", command, *(["--", *args] if args else [])])
        if result.returncode == 0:
            return True, "registered (~/.claude.json)"
        if "already exists" in (result.stderr + result.stdout):
            return True, "already registered"
        return False, result.stderr.strip() or "registration failed"

    if client.key == "hermes":
        if _hermes_registered():
            return True, "already registered"
        cmd = [binary, "mcp", "add", "loci", "--command", command]
        if args:
            cmd += ["--args", *args]
        added = _run(cmd, _HERMES_ANSWERS)
        # The command exits 0 even when it cancels, so ask the config.
        if _hermes_registered():
            return True, "registered (hermes config). Start a new session or run /reload-mcp."
        why = "timed out" if added.returncode == TIMED_OUT else "did not save it"
        return False, f"hermes {why}. Run it yourself: {manual}"

    return False, f"no registration recipe for {client.key}"


def claude_desktop_config() -> Path:
    return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def register_claude_desktop(
    command: str = "loci-mcp", args: list[str] | None = None
) -> tuple[bool, str] | None:
    """Add Loci to Claude Desktop's config, the way setup.py does for a checkout.

    Returns None when Claude Desktop is not there (no config directory), so a
    machine without it prints nothing. An existing `loci` entry is left alone,
    which keeps this idempotent and keeps a checkout's `uv run` entry from
    being overwritten by the installed script's.
    """
    path = claude_desktop_config()
    if not path.parent.is_dir():
        return None
    config: dict = {}
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False, f"{path} is not valid JSON. Add the loci entry yourself."
    servers = config.setdefault("mcpServers", {})
    if "loci" in servers:
        return True, "already registered"
    servers["loci"] = {"command": shutil.which(command) or command, "args": args or []}
    try:
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError as e:
        return False, f"could not write {path}: {e}"
    return True, f"registered ({path}). Restart Claude Desktop."


def run_register(argv: list[str] | None = None, stdin=None, stdout=None) -> int:
    """`loci register`. Returns the process exit code."""
    import argparse
    import sys

    out = stdout if stdout is not None else sys.stdout
    stream = stdin if stdin is not None else sys.stdin

    parser = argparse.ArgumentParser(
        prog="loci register",
        description="Register the Loci MCP server with your agent.",
    )
    parser.add_argument(
        "--target", default=None,
        help="claude, hermes, a comma-separated list, or all. Asked for when several agents are found.",
    )
    args = parser.parse_args(argv)

    try:
        targets = resolve_targets(args.target, stream, out)
    except TargetError as e:
        print(str(e), file=out)
        return 1

    code = 0
    for client in targets:
        ok, message = register_mcp(client)
        print(f"  {client.label}: {message}", file=out)
        code = code or (0 if ok else 1)
        if client.key == "claude":
            desktop = register_claude_desktop()
            if desktop is not None:
                print(f"  Claude Desktop: {desktop[1]}", file=out)
                code = code or (0 if desktop[0] else 1)
    return code
