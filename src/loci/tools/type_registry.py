"""
type_registry.py
Loads the Loci type ontology and provides a runtime registry of valid types.

At startup the server calls get_registry(vault_root) once. All tools that need
to validate a type — write_file, vault_linter, check_duplicate — call this
instead of referencing a hardcoded VALID_TYPES set.

Two files feed the registry:
  ontology.yaml        canonical types (reseeded on META_VERSION bumps)
  ontology-user.yaml   user-defined extensions (never reseeded)

User type safety rules (enforced at load time):
  1. extends must name a canonical type — no new roots, no extending user types
  2. name must not collide with any canonical type
  3. additive only — no redefining inherited field names
  4. one level deep — automatically guaranteed by rule 1

Invalid user type definitions are skipped with a warning; the server
continues with whatever is valid.
"""

import re
from functools import lru_cache
import sys
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


REFERENCES_DIR = Path(__file__).parent.parent / "skills" / "references"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FieldDef:
    name: str
    type: str                          # string | array | datetime | enum | boolean
    values: Optional[list[str]] = None # enum valid values; None for non-enum fields


@dataclass
class TypeDef:
    name: str
    extends: Optional[str]             # None for canonical roots
    description: str
    required_fields: list[FieldDef] = field(default_factory=list)
    optional_fields: list[FieldDef] = field(default_factory=list)
    subtype_fields: dict[str, list[FieldDef]] = field(default_factory=dict)

    def enum_constraints(self, subtype: Optional[str] = None) -> dict[str, set[str]]:
        """Return {field_name: valid_value_set} for all enum fields on this type.

        Pass subtype to include fields that only apply to a specific subtype
        (e.g. subtype='book' on an asset node includes the genre enum).
        """
        result = {}
        for f in self.required_fields + self.optional_fields:
            if f.type == "enum" and f.values:
                result[f.name] = set(f.values)
        if subtype and subtype in self.subtype_fields:
            for f in self.subtype_fields[subtype]:
                if f.type == "enum" and f.values:
                    result[f.name] = set(f.values)
        return result

    def required_names(self) -> set[str]:
        return {f.name for f in self.required_fields}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _packaged_base_fields() -> dict:
    packaged = yaml.safe_load(
        (REFERENCES_DIR / "ontology.yaml").read_text(encoding="utf-8")
    ) or {}
    return packaged.get("base_fields") or {}


class TypeRegistry:
    def __init__(self):
        self._types: dict[str, TypeDef] = {}
        self._canonical_names: set[str] = set()
        self._base_required: list[str] = []
        self._base_optional: list[str] = []
        self._warnings: list[str] = []

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        ontology_path: Path,
        user_ontology_path: Optional[Path] = None,
    ) -> "TypeRegistry":
        registry = cls()
        registry._load_canonical(ontology_path)
        if user_ontology_path and user_ontology_path.exists():
            registry._load_user(user_ontology_path)
        return registry

    def _load_canonical(self, path: Path) -> None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in raw.get("types", []):
            td = self._parse_type(entry)
            self._types[td.name] = td
            self._canonical_names.add(td.name)

        base = raw.get("base_fields")
        if not base and path != REFERENCES_DIR / "ontology.yaml":
            # A vault copy from before base_fields existed: the packaged file
            # is the source of truth for what every node carries.
            base = _packaged_base_fields()
        base = base or {}
        self._base_required = [str(n) for n in (base.get("required") or [])]
        self._base_optional = [str(n) for n in (base.get("optional") or [])]

    def _load_user(self, path: Path) -> None:
        canonical_names = set(self._types.keys())
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in (raw.get("types") or []):
            name = entry.get("name", "").strip()
            extends = entry.get("extends")

            # Rule 1: must extend a canonical type
            if not extends:
                self._warnings.append(
                    f"User type '{name}' skipped: 'extends' must name a canonical type, not null"
                )
                continue
            if extends not in canonical_names:
                self._warnings.append(
                    f"User type '{name}' skipped: parent '{extends}' is not a canonical type"
                )
                continue

            # Rule 2: no name collision with canonical
            if name in canonical_names:
                self._warnings.append(
                    f"User type '{name}' skipped: name collides with canonical type"
                )
                continue

            # Rule 3: no redefining inherited field names
            parent = self._types[extends]
            inherited_names = {f.name for f in parent.required_fields + parent.optional_fields}
            user_fields = self._parse_fields(entry.get("fields", {}))
            all_user = user_fields["required"] + user_fields["optional"]
            conflicts = [f.name for f in all_user if f.name in inherited_names]
            if conflicts:
                self._warnings.append(
                    f"User type '{name}' skipped: fields {conflicts} redefine inherited fields"
                )
                continue

            td = TypeDef(
                name=name,
                extends=extends,
                description=entry.get("description", ""),
                required_fields=parent.required_fields + user_fields["required"],
                optional_fields=parent.optional_fields + user_fields["optional"],
            )
            self._types[name] = td

    @staticmethod
    def _parse_type(entry: dict) -> TypeDef:
        fields = TypeRegistry._parse_fields(entry.get("fields", {}))
        subtype_fields: dict[str, list[FieldDef]] = {}
        for st in (entry.get("subtypes") or []):
            st_name = st.get("name")
            if st_name:
                st_parsed = TypeRegistry._parse_fields(st.get("fields", {}))
                subtype_fields[st_name] = st_parsed["required"] + st_parsed["optional"]
        return TypeDef(
            name=entry["name"],
            extends=entry.get("extends"),
            description=entry.get("description", ""),
            required_fields=fields["required"],
            optional_fields=fields["optional"],
            subtype_fields=subtype_fields,
        )

    @staticmethod
    def _parse_fields(fields_block: dict) -> dict[str, list[FieldDef]]:
        result: dict[str, list[FieldDef]] = {"required": [], "optional": []}
        for bucket in ("required", "optional"):
            for f in (fields_block.get(bucket) or []):
                if isinstance(f, dict):
                    result[bucket].append(FieldDef(
                        name=f["name"],
                        type=f.get("type", "string"),
                        values=f.get("values"),
                    ))
        return result

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def types(self) -> list["TypeDef"]:
        """Every loaded type in declaration order — canonical first, as the
        ontology file lists them, then user extensions in their file's order."""
        return list(self._types.values())

    def type_names(self) -> set[str]:
        """All valid type names (canonical + accepted user types)."""
        return set(self._types.keys())

    def get(self, name: str) -> Optional[TypeDef]:
        """Return the TypeDef for name, or None if unknown."""
        return self._types.get(name)

    def is_canonical(self, name: str) -> bool:
        """True if name came from the canonical ontology file, not a user one."""
        return name in self._canonical_names

    @property
    def base_required(self) -> list[str]:
        """Frontmatter fields every node carries, from `base_fields:` in ontology.yaml."""
        return list(self._base_required)

    @property
    def base_optional(self) -> list[str]:
        return list(self._base_optional)

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    _VALID_FIELD_TYPES = frozenset({"string", "array", "datetime", "enum", "boolean"})
    _NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")

    def validate_user_type(
        self,
        name: str,
        extends: str,
        fields: Optional[list[dict]] = None,
    ) -> dict:
        """
        Validate a proposed user type definition without writing anything.
        Returns {"valid": bool, "errors": [...], "resolved_fields": {...}}.
        Call this before writing to ontology-user.yaml.
        """
        errors: list[str] = []
        canonical_names = set(self._canonical_names)

        name = (name or "").strip()
        if not name:
            errors.append("'name' is required and must not be empty")
            return {"valid": False, "errors": errors, "resolved_fields": {"required": [], "optional": []}}
        if not self._NAME_RE.match(name):
            errors.append(
                f"'{name}' is not a valid type name — use lowercase letters, digits, and hyphens only"
            )

        if not extends:
            errors.append("'extends' is required and must name a canonical type")
        elif extends not in canonical_names:
            errors.append(
                f"'{extends}' is not a canonical type. "
                f"Valid parents: {sorted(canonical_names)}"
            )

        if name in canonical_names:
            errors.append(f"'{name}' collides with an existing canonical type")
        elif name in self._types:
            errors.append(f"'{name}' collides with an existing user-defined type")

        resolved: dict[str, list] = {"required": [], "optional": []}
        if not errors and extends in self._types:
            parent = self._types[extends]
            inherited_names = {f.name for f in parent.required_fields + parent.optional_fields}

            user_field_defs: list[FieldDef] = []
            for f in (fields or []):
                field_type = f.get("type", "string")
                if field_type not in self._VALID_FIELD_TYPES:
                    errors.append(
                        f"Field '{f['name']}': invalid type '{field_type}'. "
                        f"Must be one of: {sorted(self._VALID_FIELD_TYPES)}"
                    )
                elif f.get("name") in inherited_names:
                    errors.append(
                        f"Field '{f['name']}' redefines an inherited field from '{extends}'"
                    )
                else:
                    user_field_defs.append(FieldDef(
                        name=f["name"],
                        type=field_type,
                        values=f.get("values"),
                    ))

            if not errors:
                resolved["required"] = [
                    {"name": f.name, "type": f.type, "values": f.values}
                    for f in parent.required_fields
                ]
                resolved["optional"] = [
                    {"name": f.name, "type": f.type, "values": f.values}
                    for f in parent.optional_fields + user_field_defs
                ]

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "resolved_fields": resolved,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[TypeRegistry] = None
_registry_vault: Optional[Path] = None
_registry_mtimes: tuple = ()  # source-file mtimes observed at last load


def _source_mtimes(ontology_path: Path, user_path: Optional[Path]) -> tuple:
    """mtimes of the files the registry was built from; 0.0 for an absent overlay."""
    user_mtime = user_path.stat().st_mtime if (user_path and user_path.exists()) else 0.0
    return (ontology_path.stat().st_mtime, user_mtime)


def get_registry(vault_root: Optional[Path] = None) -> TypeRegistry:
    """
    Return the shared TypeRegistry, loading it on first call and reloading
    when either source file has changed on disk since. The `loci` HTTP server
    and `loci-mcp` are separate processes, so a type defined through one has
    to reach the other by the file's mtime — the same way nx_graph picks up
    nodes written by the other process.
    Falls back to the references directory if ontology.yaml is not in the vault.
    Pass vault_root=None to force a load from references (useful in tests).
    """
    global _registry, _registry_vault, _registry_mtimes

    if vault_root is not None:
        ontology_path = vault_root / "meta" / "ontology.yaml"
        user_path = vault_root / "meta" / "ontology-user.yaml"
    else:
        ontology_path = REFERENCES_DIR / "ontology.yaml"
        user_path = None

    # Fall back to references if vault copy not seeded yet
    if not ontology_path.exists():
        ontology_path = REFERENCES_DIR / "ontology.yaml"
        user_path = None

    mtimes = _source_mtimes(ontology_path, user_path)
    if _registry is None or _registry_vault != vault_root or _registry_mtimes != mtimes:
        _registry = TypeRegistry.load(
            ontology_path,
            user_path if (user_path and user_path.exists()) else None,
        )
        _registry_vault = vault_root
        _registry_mtimes = mtimes

    return _registry


def reset_registry() -> None:
    """Force the next get_registry() call to reload. Used in tests."""
    global _registry, _registry_vault, _registry_mtimes
    _registry = None
    _registry_vault = None
    _registry_mtimes = ()
