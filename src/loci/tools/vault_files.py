"""
Which files in a vault folder are not notes although their name says `.md`.

macOS writes `._name` next to a file it copies onto a volume without extended
attributes (tar, zip, SMB, exFAT, a sync client): an AppleDouble file holding
the resource fork, binary and not UTF-8. In a vault, `._note.md` matches
`*.md`; any reader that opens it as a note fails or reports it as one.
"""

from pathlib import Path


def is_appledouble(path: Path | str) -> bool:
    """True when the file name is an AppleDouble companion (`._<name>`)."""
    return Path(path).name.startswith("._")
