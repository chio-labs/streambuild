from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from streambuild.dev_server._helpers.server.static_assets import static_assets_present
from tests.unit.src.streambuild.dev_server._test_types import (
    SpaFallbackTestCase,
    StaticAssetsPresenceTestCase,
)
from tests.unit.src.streambuild.dev_server.helpers import (
    build_static_test_client,
    write_static_assets_build,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StaticAssetsPresenceTestCase(
            description="a built UI with an index shell is present",
            expected_present=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_built_assets_when_checking_presence_then_reports_present(
    test_case: StaticAssetsPresenceTestCase,
    tmp_path: Path,
) -> None:
    write_static_assets_build(assets_root=tmp_path)

    assert static_assets_present(assets_root=tmp_path) is test_case.expected_present


@pytest.mark.parametrize(
    "test_case",
    [
        StaticAssetsPresenceTestCase(
            description="a checkout without a built UI is not present",
            expected_present=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_empty_assets_root_when_checking_presence_then_reports_absent(
    test_case: StaticAssetsPresenceTestCase,
    tmp_path: Path,
) -> None:
    assert static_assets_present(assets_root=tmp_path) is test_case.expected_present


@pytest.mark.parametrize(
    "test_case",
    [
        SpaFallbackTestCase(
            description="root path serves the SPA shell",
            request_path="/",
            expected_body_fragment="stb-dev-shell",
        ),
        SpaFallbackTestCase(
            description="deep link falls back to the SPA shell",
            request_path="/lineage",
            expected_body_fragment="stb-dev-shell",
        ),
        SpaFallbackTestCase(
            description="hashed app asset is served verbatim",
            request_path="/_app/app.js",
            expected_body_fragment="stb-app-script",
        ),
        SpaFallbackTestCase(
            description="real top-level file is served verbatim",
            request_path="/robots.txt",
            expected_body_fragment="User-agent",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_built_assets_when_requesting_path_then_serves_expected_body(
    test_case: SpaFallbackTestCase,
    tmp_path: Path,
) -> None:
    write_static_assets_build(assets_root=tmp_path)
    client: TestClient = build_static_test_client(assets_root=tmp_path)

    response: Response = client.get(test_case.request_path)

    assert response.status_code == 200
    assert test_case.expected_body_fragment in response.text
