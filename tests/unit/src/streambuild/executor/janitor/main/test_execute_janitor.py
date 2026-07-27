from typing import cast

import pytest

from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterMetadataObjectKey,
    AdapterPreparedObjectMapping,
    AdapterRelationCleanupRequest,
    InspectedActiveTableBinding,
    InspectedManagedTableState,
)
from streambuild.executor.janitor.main.execute_janitor import execute_janitor
from streambuild.executor.janitor.models import (
    JanitorApplyResult,
    JanitorPreviewResult,
    JanitorRequest,
)
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.executor.janitor.main._test_types import (
    JanitorAdapterCleanupTestCase,
    JanitorCleanupResultTestCase,
    JanitorConcurrentActivationTestCase,
    JanitorUnsafeMappingTestCase,
)
from tests.unit.src.streambuild.executor.janitor.main.helpers import (
    SequencedManagedStateAdapterConnection,
    WrongCleanupAdapterConnection,
)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorAdapterCleanupTestCase(
            description="keeps active target and cleans stale relation through adapter",
            inventory=AdapterDeploymentInventory(
                deployments=(
                    AdapterDeploymentRecord(
                        deployment_id="20260727T120000Z_active1",
                        created_at="2020-01-02 00:00:00.000",
                        status="published",
                        replay_lineage_mode="offsets",
                        selected_root_keys=(),
                        warning_codes=(),
                        prepared_object_mappings=(
                            AdapterPreparedObjectMapping(
                                logical_key=AdapterMetadataObjectKey(
                                    database=None,
                                    object_type="table",
                                    name="tbl__orders_enriched",
                                ),
                                physical_name=("tbl__orders_enriched__20260727T120000Z_active1"),
                            ),
                        ),
                    ),
                    AdapterDeploymentRecord(
                        deployment_id="20260727T110000Z_stale1",
                        created_at="2020-01-01 00:00:00.000",
                        status="backfilling",
                        replay_lineage_mode="offsets",
                        selected_root_keys=(),
                        warning_codes=(),
                        prepared_object_mappings=(
                            AdapterPreparedObjectMapping(
                                logical_key=AdapterMetadataObjectKey(
                                    database=None,
                                    object_type="table",
                                    name="tbl__orders_enriched",
                                ),
                                physical_name=("tbl__orders_enriched__20260727T110000Z_stale1"),
                            ),
                        ),
                    ),
                ),
                publish_events=(),
            ),
            managed_table_state=InspectedManagedTableState(
                active_bindings=(
                    InspectedActiveTableBinding(
                        database="analytics",
                        logical_name="tbl__orders_enriched",
                        physical_name="tbl__orders_enriched__20260727T120000Z_active1",
                    ),
                ),
                physical_candidates=(),
            ),
            request=JanitorRequest(
                database="analytics",
                metadata_database="metadata",
                retention_days=7,
                apply=True,
            ),
            expected_cleanup_request=AdapterRelationCleanupRequest(
                database="analytics",
                relation_names=("tbl__orders_enriched__20260727T110000Z_stale1",),
            ),
            expected_result=JanitorApplyResult(
                database="analytics",
                retention_days=7,
                deleted_deployment_ids=("20260727T110000Z_stale1",),
                deleted_object_names=("tbl__orders_enriched__20260727T110000Z_stale1",),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_and_stale_deployments_when_applying_janitor_then_adapter_cleans_only_stale(
    test_case: JanitorAdapterCleanupTestCase,
) -> None:
    connection: RecordingAdapterConnection = RecordingAdapterConnection(
        managed_table_state=test_case.managed_table_state,
        deployment_inventory=test_case.inventory,
    )

    result: JanitorApplyResult = cast(
        JanitorApplyResult,
        execute_janitor(
            request=test_case.request,
            client=connection,
        ),
    )

    assert connection.cleanup_requests == [test_case.expected_cleanup_request]
    assert connection.statements == []
    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorCleanupResultTestCase(
            description="rejects cleanup result that omits requested stale relation",
            inventory=AdapterDeploymentInventory(
                deployments=(
                    AdapterDeploymentRecord(
                        deployment_id="20260727T110000Z_stale1",
                        created_at="2020-01-01 00:00:00.000",
                        status="backfilling",
                        replay_lineage_mode="offsets",
                        selected_root_keys=(),
                        warning_codes=(),
                        prepared_object_mappings=(
                            AdapterPreparedObjectMapping(
                                logical_key=AdapterMetadataObjectKey(
                                    database=None,
                                    object_type="table",
                                    name="tbl__orders_enriched",
                                ),
                                physical_name=("tbl__orders_enriched__20260727T110000Z_stale1"),
                            ),
                        ),
                    ),
                ),
                publish_events=(),
            ),
            request=JanitorRequest(
                database="analytics",
                metadata_database="metadata",
                retention_days=7,
                apply=True,
            ),
            returned_relation_names=(),
            expected_error_fragment=("Adapter cleanup result did not match requested relations"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_omits_cleanup_result_when_applying_janitor_then_it_rejects_success(
    test_case: JanitorCleanupResultTestCase,
) -> None:
    connection: WrongCleanupAdapterConnection = WrongCleanupAdapterConnection(
        deployment_inventory=test_case.inventory,
        returned_relation_names=test_case.returned_relation_names,
    )

    with pytest.raises(AdapterResultError, match=test_case.expected_error_fragment):
        execute_janitor(request=test_case.request, client=connection)

    assert len(connection.cleanup_requests) == 1


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorUnsafeMappingTestCase(
            description="keeps deployment whose metadata maps a different logical relation",
            inventory=AdapterDeploymentInventory(
                deployments=(
                    AdapterDeploymentRecord(
                        deployment_id="20260727T110000Z_stale1",
                        created_at="2020-01-01 00:00:00.000",
                        status="backfilling",
                        replay_lineage_mode="offsets",
                        selected_root_keys=(),
                        warning_codes=(),
                        prepared_object_mappings=(
                            AdapterPreparedObjectMapping(
                                logical_key=AdapterMetadataObjectKey(
                                    database=None,
                                    object_type="table",
                                    name="tbl__orders_enriched",
                                ),
                                physical_name=("tbl__payments_enriched__20260727T110000Z_stale1"),
                            ),
                        ),
                    ),
                ),
                publish_events=(),
            ),
            request=JanitorRequest(
                database="analytics",
                metadata_database="metadata",
                retention_days=7,
                apply=False,
            ),
            expected_deletable=False,
            expected_reason="physical mappings do not match deployment identity",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_physical_mapping_when_previewing_janitor_then_it_is_not_deletable(
    test_case: JanitorUnsafeMappingTestCase,
) -> None:
    connection: RecordingAdapterConnection = RecordingAdapterConnection(
        deployment_inventory=test_case.inventory
    )

    result: JanitorPreviewResult = cast(
        JanitorPreviewResult,
        execute_janitor(request=test_case.request, client=connection),
    )

    assert result.candidates[0].deletable is test_case.expected_deletable
    assert result.candidates[0].reason == test_case.expected_reason
    assert connection.cleanup_requests == []


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorConcurrentActivationTestCase(
            description="aborts when stale target becomes active after preview",
            inventory=AdapterDeploymentInventory(
                deployments=(
                    AdapterDeploymentRecord(
                        deployment_id="20260727T110000Z_stale1",
                        created_at="2020-01-01 00:00:00.000",
                        status="backfilling",
                        replay_lineage_mode="offsets",
                        selected_root_keys=(),
                        warning_codes=(),
                        prepared_object_mappings=(
                            AdapterPreparedObjectMapping(
                                logical_key=AdapterMetadataObjectKey(
                                    database=None,
                                    object_type="table",
                                    name="tbl__orders_enriched",
                                ),
                                physical_name=("tbl__orders_enriched__20260727T110000Z_stale1"),
                            ),
                        ),
                    ),
                ),
                publish_events=(),
            ),
            managed_states=(
                InspectedManagedTableState(active_bindings=(), physical_candidates=()),
                InspectedManagedTableState(
                    active_bindings=(
                        InspectedActiveTableBinding(
                            database="analytics",
                            logical_name="tbl__orders_enriched",
                            physical_name=("tbl__orders_enriched__20260727T110000Z_stale1"),
                        ),
                    ),
                    physical_candidates=(),
                ),
            ),
            request=JanitorRequest(
                database="analytics",
                metadata_database="metadata",
                retention_days=7,
                apply=True,
            ),
            expected_error_fragment="Refusing to clean relations that became active",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_becomes_active_when_applying_janitor_then_cleanup_aborts(
    test_case: JanitorConcurrentActivationTestCase,
) -> None:
    connection: SequencedManagedStateAdapterConnection = SequencedManagedStateAdapterConnection(
        deployment_inventory=test_case.inventory,
        managed_states=test_case.managed_states,
    )

    with pytest.raises(AdapterResultError, match=test_case.expected_error_fragment):
        execute_janitor(request=test_case.request, client=connection)

    assert connection.cleanup_requests == []
