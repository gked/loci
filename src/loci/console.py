"""Console setup shared by the `loci` and `loci-mcp` entry points."""

import sys


def use_utf8_output() -> None:
    """Make stdout and stderr write UTF-8 whatever the platform default is.

    CLI output carries non-ASCII characters (the arrow in `loci skills`, skill
    and node titles in the user's own language). When output is piped or
    redirected on Windows, Python encodes it with the ANSI code page (cp1252),
    which cannot represent them, and the command dies with UnicodeEncodeError
    halfway through. `errors="replace"` keeps a stray character from ever being
    fatal; it prints "?" instead.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # replaced by something that is not a TextIOWrapper
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # closed or detached stream
            pass
