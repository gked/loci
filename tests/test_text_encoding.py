"""Text I/O in Loci names its encoding.

Python's default text encoding is the platform's, not UTF-8: cp1252 on a stock
Windows install. The reference files, vault nodes and CLI output all carry
non-ASCII characters (em dashes, arrows, the 🔒 on every protected skill
heading, and whatever language the user writes in), so a bare `open(path)` or
`read_text()` works on macOS and raises UnicodeDecodeError on Windows.

Three layers here: a static guard so the next call cannot regress, a real
subprocess under a non-UTF-8 default for the vault-seeding path every new
install hits first, and one for the CLI's own output.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "loci"

# Modules whose open() is not file text I/O.
_NOT_FILES = {"webbrowser", "os", "io", "tarfile", "zipfile", "gzip"}


def _is_binary_open(call: ast.Call) -> bool:
    func = call.func
    index = 1 if isinstance(func, ast.Name) else 0
    mode = None
    if len(call.args) > index:
        arg = call.args[index]
        if isinstance(arg, ast.Constant):
            mode = arg.value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and "b" in mode


def _text_io_without_encoding() -> list[str]:
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name not in {"read_text", "write_text", "open"}:
                continue
            if any(kw.arg == "encoding" for kw in node.keywords):
                continue
            if name == "open":
                if _is_binary_open(node):
                    continue
                if isinstance(func, ast.Attribute) and getattr(func.value, "id", "") in _NOT_FILES:
                    continue
            offenders.append(f"{path.relative_to(SRC.parent.parent)}:{node.lineno} {name}()")
    return offenders


def test_no_text_io_without_an_explicit_encoding():
    offenders = _text_io_without_encoding()
    assert not offenders, (
        "Text I/O without encoding= uses the platform default (cp1252 on Windows). "
        "Pass encoding=\"utf-8\":\n  " + "\n  ".join(offenders)
    )


def _legacy_env(home: Path, **extra: str) -> dict[str, str]:
    """An environment whose default text encoding is not UTF-8, on any OS."""
    env = {k: v for k, v in os.environ.items() if k not in {"LOCI_VAULT_ROOT", "LOCI_CONFIG"}}
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        PYTHONUTF8="0",
        PYTHONCOERCECLOCALE="0",
        LC_ALL="C",
        LANG="C",
        **extra,
    )
    env.pop("PYTHONIOENCODING", None)
    return env


def test_creating_a_vault_works_when_the_default_encoding_is_not_utf8(tmp_path):
    code = (
        "import locale, sys\n"
        "from pathlib import Path\n"
        "from loci.tools.vault_init import create_vault_structure\n"
        "enc = locale.getpreferredencoding(False)\n"
        "assert enc.lower().replace('-', '') != 'utf8', f'test setup: default encoding is {enc}'\n"
        "create_vault_structure(Path(sys.argv[1]))\n"
        "print('meta:', len(list((Path(sys.argv[1]) / 'meta').iterdir())))\n"
    )
    vault = tmp_path / "vault"
    done = subprocess.run(
        [sys.executable, "-c", code, str(vault)],
        env=_legacy_env(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert done.returncode == 0, done.stderr[-800:]
    seeded = (vault / "meta" / "ontology.yaml").read_text(encoding="utf-8")
    assert "ontology_version" in seeded


def test_cli_output_survives_a_console_that_cannot_encode_the_arrow(tmp_path):
    """`loci skills` prints "label → path". A cp1252 stdout cannot encode that."""
    code = "import sys\nfrom loci.http_server import main\nsys.argv = ['loci', 'skills', '--target', 'claude', '--yes']\nmain()\n"
    done = subprocess.run(
        [sys.executable, "-c", code],
        env=_legacy_env(tmp_path, PYTHONIOENCODING="cp1252"),
        capture_output=True,
    )
    stderr = done.stderr.decode("utf-8", "replace")
    assert done.returncode == 0, stderr[-800:]
    assert "UnicodeEncodeError" not in stderr
    assert "→".encode("utf-8") in done.stdout
    assert (tmp_path / ".claude" / "skills" / "loci-save" / "SKILL.md").is_file()


def test_seeded_meta_files_are_written_with_lf_not_the_platform_newline(tmp_path, monkeypatch):
    """Text mode turns "\\n" into "\\r\\n" on Windows. Seeded meta files live in a
    vault that a Mac may share, so they must be byte-identical on every OS."""
    real_write_text = Path.write_text

    def windows_write_text(self, data, encoding=None, errors=None, newline=None):
        # What Windows does when newline is left at its default.
        return real_write_text(self, data, encoding=encoding, errors=errors,
                               newline="\r\n" if newline is None else newline)

    monkeypatch.setattr(Path, "write_text", windows_write_text)
    monkeypatch.delenv("LOCI_VAULT_ROOT", raising=False)

    from loci.tools.vault_init import create_vault_structure

    vault = tmp_path / "vault"
    create_vault_structure(vault)
    crlf = [p.name for p in (vault / "meta").iterdir() if b"\r\n" in p.read_bytes()]
    assert not crlf, f"seeded with CRLF: {crlf}"
