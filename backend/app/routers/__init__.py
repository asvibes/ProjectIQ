"""Router registry.

Every module in this package that exposes a module-level ``router`` (a
``fastapi.APIRouter``) is picked up automatically and mounted by ``app.main``.
To add an endpoint group, create ``app/routers/<name>.py`` containing::

    router = APIRouter(prefix="/projects", tags=["projects"])

No edits to this file or to ``main.py`` are needed.

Rules:
* Modules without a ``router`` attribute (empty placeholders, helpers) are skipped.
* Modules whose names start with ``_`` are skipped.
* A ``router`` that is not an ``APIRouter`` raises ``TypeError``; an exception raised
  while importing a router module propagates. Broken routers fail loudly at startup
  rather than silently disappearing from the API.
* Routers are registered in alphabetical module order, so the OpenAPI output is stable.

Discovery is lazy (only when ``discover_routers`` is called), so importing this package
never imports the router modules and cannot cause circular imports.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from types import ModuleType
from typing import Optional

from fastapi import APIRouter

__all__ = ["discover_routers"]


def discover_routers(package: Optional[ModuleType] = None) -> list[tuple[str, APIRouter]]:
    """Return ``(module_name, router)`` for every router module in ``package``.

    ``package`` defaults to this package; tests pass a different one.
    """
    package = package or sys.modules[__name__]
    found: list[tuple[str, APIRouter]] = []
    modules = sorted(pkgutil.iter_modules(package.__path__), key=lambda info: info.name)
    for info in modules:
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        router = getattr(module, "router", None)
        if router is None:
            continue
        if not isinstance(router, APIRouter):
            raise TypeError(
                f"{module.__name__}.router must be a fastapi.APIRouter, got {type(router).__name__}"
            )
        found.append((info.name, router))
    return found