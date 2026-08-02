from typing import cast

import pytest

from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterMetadataObjectKey,
    AdapterPreparedObjectMapping,
    AdapterPublishEventRecord,
    AdapterRelationCleanupRequest,
    AdapterStableBindingRemoval,
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
    JanitorConcurrentActivationTestCase,
    JanitorRollbackSafetyTestCase,
    JanitorUnsafeMappingTestCase,
)
from tests.unit.src.streambuild.executor.janitor.main.helpers import (
    JanitorWorkflowRecordingAdapterConnection,
    SequencedManagedStateAdapterConnection,
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
                                logical_model_name="orders_enriched",
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
                                logical_model_name="orders_enriched",
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
            expected_binding_request=AdapterBindingReplacementRequest(bindings=()),
            expected_statements=(
                "DROP TABLE IF EXISTS "
                "analytics.tbl__orders_enriched__20260727T110000Z_stale1 SYNC;",
            ),
            expected_result=JanitorApplyResult(
                database="analytics",
                retention_days=7,
                deleted_deployment_ids=("20260727T110000Z_stale1",),
                deleted_object_names=("tbl__orders_enriched__20260727T110000Z_stale1",),
            ),
        ),
        JanitorAdapterCleanupTestCase(
            description="removes leaked obsolete binding and cleans its historical deployment",
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
                                    name="orders_current",
                                ),
                                physical_name="orders_current__20260727T120000Z_active1",
                                logical_model_name="orders",
                            ),
                        ),
                    ),
                    AdapterDeploymentRecord(
                        deployment_id="20260727T110000Z_stale1",
                        created_at="2020-01-01 00:00:00.000",
                        status="published",
                        replay_lineage_mode="offsets",
                        selected_root_keys=(),
                        warning_codes=(),
                        prepared_object_mappings=(
                            AdapterPreparedObjectMapping(
                                logical_key=AdapterMetadataObjectKey(
                                    database=None,
                                    object_type="table",
                                    name="orders_legacy",
                                ),
                                physical_name="orders_legacy__20260727T110000Z_stale1",
                                logical_model_name="orders",
                            ),
                        ),
                    ),
                ),
                publish_events=(
                    AdapterPublishEventRecord(
                        deployment_id="20260727T110000Z_stale1",
                        published_at="2020-01-01 01:00:00.000",
                        logical_view_names=("orders_legacy",),
                    ),
                    AdapterPublishEventRecord(
                        deployment_id="20260727T120000Z_active1",
                        published_at="2020-01-02 01:00:00.000",
                        logical_view_names=("orders_current",),
                    ),
                ),
            ),
            managed_table_state=InspectedManagedTableState(
                active_bindings=(
                    InspectedActiveTableBinding(
                        database="analytics",
                        logical_name="orders_legacy",
                        physical_name="orders_legacy__20260727T110000Z_stale1",
                    ),
                    InspectedActiveTableBinding(
                        database="analytics",
                        logical_name="orders_current",
                        physical_name="orders_current__20260727T120000Z_active1",
                    ),
                ),
                physical_candidates=(),
            ),
            request=JanitorRequest(
                database="analytics",
                metadata_database="metadata",
                retention_days=0,
                apply=True,
            ),
            expected_cleanup_request=AdapterRelationCleanupRequest(
                database="analytics",
                relation_names=("orders_legacy__20260727T110000Z_stale1",),
            ),
            expected_binding_request=AdapterBindingReplacementRequest(
                bindings=(),
                removals=(
                    AdapterStableBindingRemoval(
                        database="analytics",
                        logical_name="orders_legacy",
                    ),
                ),
            ),
            expected_statements=(
                "DROP VIEW IF EXISTS analytics.orders_legacy SYNC;",
                "DROP TABLE IF EXISTS analytics.orders_legacy__20260727T110000Z_stale1 SYNC;",
            ),
            expected_result=JanitorApplyResult(
                database="analytics",
                retention_days=0,
                deleted_deployment_ids=("20260727T110000Z_stale1",),
                deleted_object_names=("orders_legacy__20260727T110000Z_stale1",),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_active_and_stale_deployments_when_applying_janitor_then_adapter_cleans_only_stale(
    test_case: JanitorAdapterCleanupTestCase,
) -> None:
    connection: JanitorWorkflowRecordingAdapterConnection = (
        JanitorWorkflowRecordingAdapterConnection(
            managed_table_state=test_case.managed_table_state,
            deployment_inventory=test_case.inventory,
        )
    )

    result: JanitorApplyResult = cast(
        JanitorApplyResult,
        execute_janitor(
            request=test_case.request,
            client=connection,
        ),
    )

    assert connection.cleanup_requests == [test_case.expected_cleanup_request]
    assert connection.binding_requests == [test_case.expected_binding_request]
    assert tuple(connection.statements) == test_case.expected_statements
    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorRollbackSafetyTestCase(
            description="protects an explicitly republished older deployment after rollback",
            inventory=AdapterDeploymentInventory(
                deployments=(
                    AdapterDeploymentRecord(
                        deployment_id="20260727T110000Z_older1",
                        created_at="2020-01-01 00:00:00.000",
                        status="published",
                        replay_lineage_mode="offsets",
                        selected_root_keys=(),
                        warning_codes=(),
                        prepared_object_mappings=(
                            AdapterPreparedObjectMapping(
                                logical_key=AdapterMetadataObjectKey(
                                    database=None,
                                    object_type="table",
                                    name="orders",
                                ),
                                physical_name="orders__20260727T110000Z_older1",
                                logical_model_name="orders",
                            ),
                        ),
                    ),
                    AdapterDeploymentRecord(
                        deployment_id="20260727T120000Z_newer1",
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
                                    name="orders",
                                ),
                                physical_name="orders__20260727T120000Z_newer1",
                                logical_model_name="orders",
                            ),
                        ),
                    ),
                ),
                publish_events=(
                    AdapterPublishEventRecord(
                        deployment_id="20260727T120000Z_newer1",
                        published_at="2020-01-02 01:00:00.000",
                        logical_view_names=("orders",),
                    ),
                    AdapterPublishEventRecord(
                        deployment_id="20260727T110000Z_older1",
                        published_at="2020-01-03 01:00:00.000",
                        logical_view_names=("orders",),
                    ),
                ),
            ),
            managed_table_state=InspectedManagedTableState(
                active_bindings=(
                    InspectedActiveTableBinding(
                        database="analytics",
                        logical_name="orders",
                        physical_name="orders__20260727T110000Z_older1",
                    ),
                ),
                physical_candidates=(),
            ),
            preview_request=JanitorRequest(
                database="analytics",
                metadata_database="metadata",
                retention_days=10000,
                apply=False,
            ),
            apply_request=JanitorRequest(
                database="analytics",
                metadata_database="metadata",
                retention_days=0,
                apply=True,
            ),
            expected_preview_states=(
                (
                    "20260727T120000Z_newer1",
                    False,
                    "published within retention window (10000 days)",
                ),
                (
                    "20260727T110000Z_older1",
                    False,
                    "contains currently active relation",
                ),
            ),
            expected_cleanup_request=AdapterRelationCleanupRequest(
                database="analytics",
                relation_names=("orders__20260727T120000Z_newer1",),
            ),
            expected_binding_request=AdapterBindingReplacementRequest(bindings=()),
            expected_statements=(
                "DROP TABLE IF EXISTS analytics.orders__20260727T120000Z_newer1 SYNC;",
            ),
            expected_result=JanitorApplyResult(
                database="analytics",
                retention_days=0,
                deleted_deployment_ids=("20260727T120000Z_newer1",),
                deleted_object_names=("orders__20260727T120000Z_newer1",),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_newer_then_older_publish_when_running_janitor_then_rollback_target_stays_active(
    test_case: JanitorRollbackSafetyTestCase,
) -> None:
    preview_connection: RecordingAdapterConnection = RecordingAdapterConnection(
        managed_table_state=test_case.managed_table_state,
        deployment_inventory=test_case.inventory,
    )
    apply_connection: JanitorWorkflowRecordingAdapterConnection = (
        JanitorWorkflowRecordingAdapterConnection(
            managed_table_state=test_case.managed_table_state,
            deployment_inventory=test_case.inventory,
        )
    )

    preview_result: JanitorPreviewResult = cast(
        JanitorPreviewResult,
        execute_janitor(request=test_case.preview_request, client=preview_connection),
    )
    apply_result: JanitorApplyResult = cast(
        JanitorApplyResult,
        execute_janitor(request=test_case.apply_request, client=apply_connection),
    )

    assert (
        tuple(
            (candidate.deployment_id, candidate.deletable, candidate.reason)
            for candidate in preview_result.candidates
        )
        == test_case.expected_preview_states
    )
    assert apply_connection.cleanup_requests == [test_case.expected_cleanup_request]
    assert apply_connection.binding_requests == [test_case.expected_binding_request]
    assert tuple(apply_connection.statements) == test_case.expected_statements
    assert apply_result == test_case.expected_result


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
                                logical_model_name="orders_enriched",
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
                                logical_model_name="orders_enriched",
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
    assert connection.binding_requests == []
    assert connection.statements == []
