"""
scheme_registry.py
Loads the Loci location scheme vocabulary and provides a runtime registry of
valid schemes, their required/optional fields, and their declared capabilities.

Two files feed the registry:
  scheme-dictionary.yaml       canonical schemes (reseeded on META_VERSION bumps)
  scheme-dictionary-user.yaml  user-defined additions (never reseeded)

User scheme safety rules (enforced at load time):
  1. name must not collide with any canonical scheme
  2. additive only — canonical definitions cannot be changed here
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


REFERENCES_DIR = Path(__file__).parent.parent / "skills" / "references"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SchemeDef:
    name: str
    description: str
    required_fields: list = field(default_factory=list)
    optional_fields: list = field(default_factory=list)
    capabilities: list = field(default_factory=list)  # subset of ["resolve", "enumerate"]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class SchemeRegistry:
    def __init__(self):
        self._schemes: dict[str, SchemeDef] = {}
        self._canonical_names: set[str] = set()
        self._warnings: list[str] = []

    @classmethod
    def load(
        cls,
        canonical_path: Path,
        user_path: Optional[Path] = None,
    ) -> "SchemeRegistry":
        registry = cls()
        registry._load_canonical(canonical_path)
        if user_path and user_path.exists():
            registry._load_user(user_path)
        return registry

    def _load_canonical(self, path: Path) -> None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in (raw.get("schemes") or []):
            sd = self._parse_scheme(entry)
            self._schemes[sd.name] = sd
            self._canonical_names.add(sd.name)

    def _load_user(self, path: Path) -> None:
        canonical_names = set(self._schemes.keys())
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in (raw.get("schemes") or []):
            name = entry.get("name", "").strip()
            if not name:
                self._warnings.append("User scheme skipped: missing 'name'")
                continue
            if name in canonical_names:
                self._warnings.append(
                    f"User scheme '{name}' skipped: name collides with a canonical scheme"
                )
                continue
            sd = self._parse_scheme(entry)
            self._schemes[sd.name] = sd

    @staticmethod
    def _parse_scheme(entry: dict) -> SchemeDef:
        return SchemeDef(
            name=entry["name"],
            description=entry.get("description", "").strip(),
            required_fields=list(entry.get("required_fields") or []),
            optional_fields=list(entry.get("optional_fields") or []),
            capabilities=list(entry.get("capabilities") or []),
        )

    def is_valid(self, name: str) -> bool:
        """True if name is a recognised scheme (canonical or user-defined)."""
        return name in self._schemes

    def get(self, name: str) -> Optional[SchemeDef]:
        """Return the SchemeDef for name, or None if unknown."""
        return self._schemes.get(name)

    def scheme_names(self) -> set[str]:
        """All valid scheme names (canonical + accepted user schemes)."""
        return set(self._schemes.keys())

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[SchemeRegistry] = None
_registry_vault: Optional[Path] = None


def get_scheme_registry(vault_root: Optional[Path] = None) -> SchemeRegistry:
    """
    Return the shared SchemeRegistry, loading it on first call.
    Falls back to the references directory if scheme-dictionary.yaml is not
    in the vault. Pass vault_root=None to force a load from references.
    """
    global _registry, _registry_vault

    if vault_root is not None:
        canonical_path = vault_root / "meta" / "scheme-dictionary.yaml"
        user_path = vault_root / "meta" / "scheme-dictionary-user.yaml"
    else:
        canonical_path = REFERENCES_DIR / "scheme-dictionary.yaml"
        user_path = None

    if not canonical_path.exists():
        canonical_path = REFERENCES_DIR / "scheme-dictionary.yaml"
        user_path = None

    if _registry is None or _registry_vault != vault_root:
        _registry = SchemeRegistry.load(
            canonical_path,
            user_path if (user_path and user_path.exists()) else None,
        )
        _registry_vault = vault_root

    return _registry


def reset_scheme_registry() -> None:
    """Force the next get_scheme_registry() call to reload. Used in tests."""
    global _registry, _registry_vault
    _registry = None
    _registry_vault = None
