"""
resolvers/url_resolver.py
Resolver for the 'url' scheme — plain HTTP/HTTPS URLs.

location fields:
  url  (required) — the full HTTP or HTTPS URL to fetch

No enumerate capability: a bare URL is a single resource, not a container.
"""

import httpx

from .base import Resolver

_TIMEOUT = 30.0


class UrlResolver(Resolver):
    capabilities = ["resolve"]

    def resolve(self, location: dict) -> dict:
        url = location.get("url")
        if not url:
            raise ValueError("UrlResolver: location missing required 'url' field")
        # No allowlist for private/metadata IPs — acceptable for a local desktop tool.
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"UrlResolver: unsupported URL scheme in '{url}'")
        with httpx.Client(follow_redirects=True, timeout=_TIMEOUT) as client:
            response = client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "application/octet-stream")
        mime_type = content_type.split(";")[0].strip()
        body = response.content
        return {
            "scheme": "url",
            "url": str(response.url),
            "content": body,
            "mime_type": mime_type,
            "size_bytes": len(body),
            "metadata": {
                "status_code": response.status_code,
                "headers": dict(response.headers),
            },
        }

    def enumerate(self, scope: dict) -> list:
        raise NotImplementedError("UrlResolver does not support enumerate")
