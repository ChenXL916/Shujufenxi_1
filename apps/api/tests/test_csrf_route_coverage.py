from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi.routing import APIRoute

from app.auth.dependencies import get_access_scope, require_csrf
from app.main import app

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _api_routes(router: Any) -> Iterator[APIRoute]:
    for route in router.routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _api_routes(original_router)
        elif isinstance(route, APIRoute):
            yield route


def _dependency_calls(dependant: Any) -> set[Any]:
    calls = {dependant.call}
    for dependency in dependant.dependencies:
        calls.update(_dependency_calls(dependency))
    return calls


def test_every_cookie_authenticated_write_route_enforces_csrf() -> None:
    unsafe_routes = [
        route for route in _api_routes(app) if set(route.methods or ()) & UNSAFE_METHODS
    ]
    missing = []
    for route in unsafe_routes:
        calls = _dependency_calls(route.dependant)
        if get_access_scope not in calls and require_csrf not in calls:
            missing.append((sorted(set(route.methods or ()) & UNSAFE_METHODS), route.path))

    assert len(unsafe_routes) == 33
    assert missing == []
