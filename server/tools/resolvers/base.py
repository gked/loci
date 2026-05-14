"""
resolvers/base.py
Abstract base class for location scheme resolvers.

Each resolver:
  - declares its capabilities (subset of ["resolve", "enumerate"])
  - implements resolve() if it supports the resolve capability
  - implements enumerate() if it supports the enumerate capability

resolve(location) -> dict
  location: a has_asset location dict (scheme + scheme-specific fields)
  returns:  {path?, content?, mime_type?, size_bytes?, metadata}
  raises:   FileNotFoundError if the item doesn't exist
            ValueError if required fields are missing

enumerate(scope) -> list[dict]
  scope:   a dict with at minimum {"scheme": ..., <scope-specific fields>}
           for local: {"scheme": "local", "path": "<dir relative to loci root>"}
  returns: list of {scheme, <identifiers>, title?}
  raises:  NotADirectoryError / ValueError as appropriate
"""

from abc import ABC, abstractmethod


class Resolver(ABC):
    capabilities: list = []  # declare which of ["resolve", "enumerate"] are supported

    @abstractmethod
    def resolve(self, location: dict) -> dict:
        raise NotImplementedError(f"{type(self).__name__} does not support resolve")

    @abstractmethod
    def enumerate(self, scope: dict) -> list:
        raise NotImplementedError(f"{type(self).__name__} does not support enumerate")
