"""
resolvers/dispatcher.py
Routes location resolve/enumerate calls to the appropriate scheme resolver.

Usage:
    from loci.tools.resolvers.dispatcher import dispatch_resolve, dispatch_enumerate

    result = dispatch_resolve({"scheme": "local", "path": "assets/abc.pdf"}, loci_root)
    items  = dispatch_enumerate({"scheme": "local", "path": "assets/"}, loci_root)

Resolver registration is static. To add a new scheme in Phase 3+:
  1. Create resolvers/<name>_resolver.py implementing Resolver (both resolve and enumerate,
     raising NotImplementedError for unsupported operations).
  2. Add an entry to _RESOLVER_FACTORIES below.
     - If the resolver needs loci_root: add the class directly (its __init__ must accept
       loci_root as its only argument).
     - If it doesn't need loci_root: wrap it — e.g. "url": lambda _root: UrlResolver()
"""

from pathlib import Path
from typing import Callable

from .base import Resolver
from .external_resolver import ExternalResolver
from .local_resolver import LocalResolver
from .url_resolver import UrlResolver


def _external(scheme: str) -> Callable[[Path], Resolver]:
    return lambda _root: ExternalResolver(scheme)


# Maps scheme name → factory callable(loci_root: Path) -> Resolver.
# LocalResolver.__init__(loci_root) matches the factory signature directly.
# Resolvers that don't need loci_root are wrapped: lambda _root: MyResolver()
# External schemes (cloud services, remote hosts) use ExternalResolver — Loci stores
# the location pointer only; access is handled by the appropriate MCP or native tool.
_RESOLVER_FACTORIES: dict[str, Callable[[Path], Resolver]] = {
    "local": LocalResolver,
    "url": lambda _root: UrlResolver(),
    "google-drive": _external("google-drive"),
    "nextcloud": _external("nextcloud"),
    "gmail": _external("gmail"),
    "icloud-drive": _external("icloud-drive"),
    "onedrive": _external("onedrive"),
    "dropbox": _external("dropbox"),
    "s3": _external("s3"),
    "ssh-remote": _external("ssh-remote"),
}


def _make_resolver(scheme: str, loci_root: Path) -> Resolver:
    factory = _RESOLVER_FACTORIES.get(scheme)
    if factory is None:
        raise ValueError(f"No resolver registered for scheme '{scheme}'")
    return factory(loci_root)


def dispatch_resolve(location: dict, loci_root: Path) -> dict:
    """
    Resolve a single location to content or metadata.
    Raises ValueError for unknown/non-resolvable schemes, FileNotFoundError if
    the item doesn't exist.
    """
    scheme = location.get("scheme")
    if not scheme:
        raise ValueError("Location is missing 'scheme' field")
    resolver = _make_resolver(scheme, loci_root)
    if "resolve" not in resolver.capabilities:
        raise ValueError(f"Scheme '{scheme}' does not support resolve")
    return resolver.resolve(location)


def dispatch_enumerate(scope: dict, loci_root: Path) -> list:
    """
    Enumerate items in a container (directory, folder, label, etc.).
    Raises ValueError for unknown/non-enumerable schemes.
    """
    scheme = scope.get("scheme")
    if not scheme:
        raise ValueError("Scope is missing 'scheme' field")
    resolver = _make_resolver(scheme, loci_root)
    if "enumerate" not in resolver.capabilities:
        raise ValueError(f"Scheme '{scheme}' does not support enumerate")
    return resolver.enumerate(scope)


def registered_schemes() -> set:
    """Return the set of scheme names with a registered resolver implementation."""
    return set(_RESOLVER_FACTORIES.keys())
