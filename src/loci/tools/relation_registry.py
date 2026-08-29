"""
relation_registry.py
Loads the Loci relation vocabulary and provides a runtime registry of valid
relation types.

Two files feed the registry:
  relation-dictionary.yaml       canonical relation types (reseeded on META_VERSION bumps)
  relation-dictionary-user.yaml  user-defined additions (never reseeded)

User relation safety rules (enforced at load time):
  1. name must not collide with any canonical relation type
  2. additive only — canonical definitions cannot be changed here

Invalid user relation definitions are skipped with a warning; the server
continues with whatever is valid.
"""

import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


REFERENCES_DIR = Path(__file__).parent.parent / "skills" / "references"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RelationDef:
    name: str
    description: str
    group: str = ""
    inverse_of: Optional[str] = None  # name of the inverse relation, if any


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class RelationRegistry:
    def __init__(self):
        self._relations: dict[str, RelationDef] = {}
        self._canonical_names: set[str] = set()
        self._warnings: list[str] = []

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        canonical_path: Path,
        user_path: Optional[Path] = None,
    ) -> "RelationRegistry":
        registry = cls()
        registry._load_canonical(canonical_path)
        if user_path and user_path.exists():
            registry._load_user(user_path)
        return registry

    def _load_canonical(self, path: Path) -> None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in raw.get("relations", []):
            rd = self._parse_relation(entry)
            self._relations[rd.name] = rd
            self._canonical_names.add(rd.name)

    def _load_user(self, path: Path) -> None:
        canonical_names = set(self._relations.keys())
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in (raw.get("relations") or []):
            name = entry.get("name", "").strip()
            if not name:
                self._warnings.append("User relation skipped: missing 'name'")
                continue

            if name in canonical_names:
                self._warnings.append(
                    f"User relation '{name}' skipped: name collides with a canonical relation"
                )
                continue

            rd = self._parse_relation(entry)
            self._relations[rd.name] = rd

    @staticmethod
    def _parse_relation(entry: dict) -> RelationDef:
        return RelationDef(
            name=entry["name"],
            description=entry.get("description", "").strip(),
            group=entry.get("group", ""),
            inverse_of=entry.get("inverse_of"),
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def relation_names(self) -> set[str]:
        """All valid relation type names (canonical + accepted user types)."""
        return set(self._relations.keys())

    def get(self, name: str) -> Optional[RelationDef]:
        """Return the RelationDef for name, or None if unknown."""
        return self._relations.get(name)

    def is_canonical(self, name: str) -> bool:
        """True if name is a canonical (non-user-defined) relation."""
        return name in self._relations and name not in self._user_names()

    def is_valid(self, name: str) -> bool:
        """True if name is a recognised relation type (canonical or user-defined)."""
        return name in self._relations

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    def validate_user_relation(
        self,
        name: str,
        group: str = "",
        description: str = "",
        inverse_of: Optional[str] = None,
    ) -> dict:
        """
        Validate a proposed user relation definition without writing anything.
        Returns {"valid": bool, "errors": [...], "warnings": [...]}.
        """
        errors: list[str] = []
        warnings: list[str] = []

        name = (name or "").strip()
        if not name:
            errors.append("'name' is required and must not be empty")
            return {"valid": False, "errors": errors, "warnings": warnings}

        if name in self._canonical_names:
            errors.append(f"'{name}' collides with a canonical relation")
        elif name in self._relations:
            errors.append(f"'{name}' collides with an existing user-defined relation")

        if inverse_of is not None:
            if inverse_of not in self._relations:
                warnings.append(
                    f"'inverse_of' names '{inverse_of}' which is not yet a known relation"
                )
            else:
                inv_def = self._relations[inverse_of]
                if inv_def.inverse_of and inv_def.inverse_of != name:
                    warnings.append(
                        f"'{inverse_of}' declares inverse_of='{inv_def.inverse_of}', "
                        f"not '{name}' — inverse pair is asymmetric"
                    )

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _user_names(self) -> set[str]:
        return set(self._relations.keys()) - self._canonical_names


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[RelationRegistry] = None
_registry_vault: Optional[Path] = None


def get_relation_registry(vault_root: Optional[Path] = None) -> RelationRegistry:
    """
    Return the shared RelationRegistry, loading it on first call.
    Falls back to the references directory if relation-dictionary.yaml is not
    in the vault. Pass vault_root=None to force a load from references.
    """
    global _registry, _registry_vault

    if vault_root is not None:
        canonical_path = vault_root / "meta" / "relation-dictionary.yaml"
        user_path = vault_root / "meta" / "relation-dictionary-user.yaml"
    else:
        canonical_path = REFERENCES_DIR / "relation-dictionary.yaml"
        user_path = None

    # Fall back to references if vault copy not seeded yet
    if not canonical_path.exists():
        canonical_path = REFERENCES_DIR / "relation-dictionary.yaml"
        user_path = None

    if _registry is None or _registry_vault != vault_root:
        _registry = RelationRegistry.load(
            canonical_path,
            user_path if (user_path and user_path.exists()) else None,
        )
        _registry_vault = vault_root

    return _registry


def reset_relation_registry() -> None:
    """Force the next get_relation_registry() call to reload. Used in tests."""
    global _registry, _registry_vault
    _registry = None
    _registry_vault = None
