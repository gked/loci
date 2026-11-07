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

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Same marker skills_install uses to recognise stubs this installer wrote.
SKILL_NAME_PREFIX = "loci-"

# Two newlines: `hermes mcp add` asks "enable all tools?" and, when it cannot
# reach the server yet, "save anyway?". Both are yes for a fresh registration.
_HERMES_ANSWERS = "y\ny\n"


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
        """True when Loci stubs are already in this agent's skills directory."""
        root = self.skills_root()
        if not root.is_dir():
            return False
        return any(
            d.name.startswith(SKILL_NAME_PREFIX) and (d / "SKILL.md").is_file()
            for d in root.iterdir()
        )


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

def _run(cmd: list[str], stdin_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin_text, capture_output=True, text=True)


def _hermes_registered() -> bool:
    binary = shutil.which("hermes")
    if not binary:
        return False
    result = _run([binary, "config", "get", "mcp_servers.loci"])
    return result.returncode == 0 and ("command:" in result.stdout or "url:" in result.stdout)


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
        _run(cmd, _HERMES_ANSWERS)
        # The command exits 0 even when it cancels, so ask the config.
        if _hermes_registered():
            return True, "registered (hermes config). Start a new session or run /reload-mcp."
        return False, f"hermes did not save it. Run it yourself: {manual}"

    return False, f"no registration recipe for {client.key}"


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
    return code
