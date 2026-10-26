from pathlib import Path

import pytest

from streambuild.compiler.planner.models import DirectWarehouseSnapshot
from streambuild.executor.direct.main.drifted_managed_source_owners import (
    drifted_managed_source_owners,
)
from streambuild.executor.direct.models import DirectBuildRequest
from tests.unit.src.streambuild.executor.direct.main._test_types import (
    DirectDriftedSourceOwnerTestCase,
)
from tests.unit.src.streambuild.executor.direct.main.helpers import (
    build_managed_source_execution_request,
    build_managed_source_snapshot,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectDriftedSourceOwnerTestCase(
            description="a declared setting absent from the deployed source names its reader",
            declared_settings=(("kafka_max_block_size", "500"),),
            catalog_setting_overrides=(),
            omitted_catalog_settings=("kafka_max_block_size",),
            extra_landing_columns=(),
            expected_owner_pipelines=("pl__orders",),
        ),
        DirectDriftedSourceOwnerTestCase(
            description="a changed topic names only the direct reader, not a downstream pipeline",
            declared_settings=(),
            catalog_setting_overrides=(("kafka_topic_list", "source.orders.previous"),),
            omitted_catalog_settings=(),
            extra_landing_columns=(),
            expected_owner_pipelines=("pl__orders",),
        ),
        DirectDriftedSourceOwnerTestCase(
            description="a deployed source matching its declaration names no pipeline",
            declared_settings=(("kafka_max_block_size", "500"),),
            catalog_setting_overrides=(),
            omitted_catalog_settings=(),
            extra_landing_columns=(),
            expected_owner_pipelines=(),
        ),
        DirectDriftedSourceOwnerTestCase(
            description="a masked deployed setting is not drift",
            declared_settings=(),
            catalog_setting_overrides=(("kafka_broker_list", "[HIDDEN]"),),
            omitted_catalog_settings=(),
            extra_landing_columns=(),
            expected_owner_pipelines=(),
        ),
        DirectDriftedSourceOwnerTestCase(
            description="a different consumer group alone is not settings drift",
            declared_settings=(),
            catalog_setting_overrides=(("kafka_group_name", "streambuild_orders_previous"),),
            omitted_catalog_settings=(),
            extra_landing_columns=(),
            expected_owner_pipelines=(),
        ),
        DirectDriftedSourceOwnerTestCase(
            description="landing column drift alone is not settings drift",
            declared_settings=(),
            catalog_setting_overrides=(),
            omitted_catalog_settings=(),
            extra_landing_columns=(("legacy_note", "String"),),
            expected_owner_pipelines=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deployed_managed_source_when_naming_drifted_owners_then_only_readers_are_named(
    test_case: DirectDriftedSourceOwnerTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_managed_source_execution_request(
        project_root=tmp_path,
        declared_settings=test_case.declared_settings,
    )
    snapshot: DirectWarehouseSnapshot = build_managed_source_snapshot(
        request=request,
        catalog_setting_overrides=test_case.catalog_setting_overrides,
        omitted_catalog_settings=test_case.omitted_catalog_settings,
        extra_landing_columns=test_case.extra_landing_columns,
    )

    owners: tuple[str, ...] = drifted_managed_source_owners(
        realized_project=request.realized_project,
        catalog=snapshot.catalog,
    )

    assert owners == test_case.expected_owner_pipelines
