"""Characterize the public route metadata exposed by the Studio router."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args, get_origin

from fastapi.routing import APIRoute

from api.routers.studio import router


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "studio_routes.json"


def _qualified_name(value: Any) -> str | None:
    if value is None:
        return None

    origin = get_origin(value)
    if origin is not None:
        arguments = ", ".join(
            qualified_name
            for argument in get_args(value)
            if (qualified_name := _qualified_name(argument)) is not None
        )
        return f"{_qualified_name(origin)}[{arguments}]"

    module = getattr(value, "__module__", None)
    qualname = getattr(value, "__qualname__", None)
    return f"{module}.{qualname}" if module and qualname else repr(value)


def _route_contract() -> list[dict[str, Any]]:
    return [
        {
            "path": route.path,
            "methods": sorted(route.methods or ()),
            "endpoint_name": route.name,
            "response_model": _qualified_name(route.response_model),
            "status_code": int(route.status_code) if route.status_code is not None else 200,
        }
        for route in router.routes
        if isinstance(route, APIRoute)
    ]


def _serialize_route_contract(contract: list[dict[str, Any]]) -> str:
    return json.dumps(contract, indent=2, ensure_ascii=True) + "\n"


def _assert_route_contract_matches_fixture(fixture_path: Path) -> None:
    actual = _serialize_route_contract(_route_contract())
    expected = _serialize_route_contract(
        json.loads(fixture_path.read_text(encoding="utf-8"))
    )

    assert actual == expected


def test_studio_router_contract_matches_committed_fixture() -> None:
    _assert_route_contract_matches_fixture(FIXTURE_PATH)


def test_studio_router_contract_accepts_crlf_fixture(tmp_path: Path) -> None:
    crlf_fixture = tmp_path / FIXTURE_PATH.name
    crlf_fixture.write_bytes(FIXTURE_PATH.read_bytes().replace(b"\n", b"\r\n"))

    _assert_route_contract_matches_fixture(crlf_fixture)
