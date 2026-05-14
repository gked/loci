"""
resolvers/external_resolver.py
Pass-through resolver for schemes whose content Loci does not fetch directly.

For cloud services (Google Drive, Gmail, S3, etc.) and remote hosts, Loci's role
is to store the location pointer in has_asset frontmatter. Actual access happens
through the appropriate MCP server or native tool for each service.

resolve() returns the location dict with a 'resolution: external' marker so the
caller knows to route to the right tool.
enumerate() raises NotImplementedError — enumeration of external sources is
handled outside Loci (e.g. via sync_locations in Phase 3).
"""

from .base import Resolver


class ExternalResolver(Resolver):
    capabilities = ["resolve"]

    def __init__(self, scheme: str):
        self.scheme = scheme

    def resolve(self, location: dict) -> dict:
        return {**location, "resolution": "external"}

    def enumerate(self, scope: dict) -> list:
        raise NotImplementedError(
            f"Scheme '{self.scheme}' enumeration is handled externally"
        )
