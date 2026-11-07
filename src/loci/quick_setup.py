"""
`loci setup`: skills and MCP registration in one command.

Nothing new happens here. It is `loci skills` followed by `loci register`, with
the choice of agents made once and handed to both, so a fresh install is

    uv tool install loci-vault
    loci setup

Running the command is the consent, so the skill install does not ask a second
time. The vault is not set up here: the agent does that when told where it
should live (`set_vault_root`).
"""

from __future__ import annotations

import argparse
import sys

from loci import clients, skills_install


def run(argv: list[str] | None = None, stdin=None, stdout=None) -> int:
    """`loci setup`. Returns the process exit code."""
    out = stdout if stdout is not None else sys.stdout
    stream = stdin if stdin is not None else sys.stdin

    parser = argparse.ArgumentParser(
        prog="loci setup",
        description="Install the Loci skills and register the MCP server with your agent(s).",
    )
    parser.add_argument(
        "--target", default=None,
        help="claude, hermes, a comma-separated list, or all. Asked for when several agents are found.",
    )
    args = parser.parse_args(argv)

    try:
        targets = clients.resolve_targets(args.target, stream, out)
    except clients.TargetError as e:
        print(str(e), file=out)
        return 1
    spec = ",".join(c.key for c in targets)

    print("Skills", file=out)
    try:
        code = skills_install.run(["--target", spec, "--yes"], stdin=stream, stdout=out)
    except OSError as e:
        print(f"  Failed: {e}", file=out)
        code = 1
    print("MCP server", file=out)
    code = clients.run_register(["--target", spec], stdin=stream, stdout=out) or code

    print("", file=out)
    if code == 0:
        restart = " and ".join(dict.fromkeys(c.restart for c in targets))
        print(f"Done. Restart {restart}, then tell the agent where the vault should live:", file=out)
        print('  "point Loci at ~/loci/vault"', file=out)
    else:
        print("Finished with problems; see above. Fix them and run `loci setup` again (it is safe to repeat).", file=out)
    return code
