from collections.abc import Iterator

from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterMetadataObjectKey,
    AdapterOwnedResourceEvent,
    AdapterPreparedObjectMapping,
    AdapterPublishEventRecord,
    AdapterRelationCleanupRequest,
    AdapterStableBinding,
    CatalogRelation,
    InspectedActiveTableBinding,
    InspectedManagedTableState,
    InspectedPhysicalTableCandidate,
)
from streambuild.executor.janitor.models import JanitorRequest
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.executor.janitor.main._test_types import (
    JanitorUnavailableRollbackTestCase,
)


class SequencedManagedStateAdapterConnection(RecordingAdapterConnection):
    def __init__(
        self,
        *,
        deployment_inventory: AdapterDeploymentInventory,
        managed_states: tuple[InspectedManagedTableState, ...],
    ) -> None:
        super().__init__(deployment_inventory=deployment_inventory)
        self._managed_states: Iterator[InspectedManagedTableState] = iter(managed_states)

    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        del database
        return next(self._managed_states)


class JanitorWorkflowRecordingAdapterConnection(RecordingAdapterConnection):
    def __init__(
        self,
        *,
        deployment_inventory: AdapterDeploymentInventory,
        managed_table_state: InspectedManagedTableState,
        relations: tuple[CatalogRelation, ...] = (),
    ) -> None:
        super().__init__(
            deployment_inventory=deployment_inventory,
            managed_table_state=managed_table_state,
            relations=relations,
        )
        self.ownership_events: list[AdapterOwnedResourceEvent] = []

    def render_replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> tuple[str, ...]:
        self.binding_requests.append(request)
        return tuple(
            f"DROP VIEW IF EXISTS {removal.database}.{removal.logical_name} SYNC;"
            for removal in request.removals
        )

    def render_cleanup_relations(self, request: AdapterRelationCleanupRequest) -> tuple[str, ...]:
        self.cleanup_requests.append(request)
        return tuple(
            f"DROP TABLE IF EXISTS {request.database}.{relation_name} SYNC;"
            for relation_name in request.relation_names
        )

    def render_owned_resource_events(
        self, *, database: str, events: tuple[AdapterOwnedResourceEvent, ...]
    ) -> tuple[str, ...]:
        del database
        self.ownership_events.extend(events)
        return ()


def unavailable_rollback_test_case() -> JanitorUnavailableRollbackTestCase:
    active_id: str = "20260727T130000Z_active1"
    missing_id: str = "20260727T120000Z_missing1"
    usable_id: str = "20260727T110000Z_usable1"
    return JanitorUnavailableRollbackTestCase(
        description="skips missing newer publication and retains older usable rollback target",
        inventory=AdapterDeploymentInventory(
            deployments=tuple(
                _rollback_retention_deployment(deployment_id=deployment_id, created_at=created_at)
                for deployment_id, created_at in (
                    (active_id, "2020-01-03 00:00:00.000"),
                    (missing_id, "2020-01-02 00:00:00.000"),
                    (usable_id, "2020-01-01 00:00:00.000"),
                )
            ),
            publish_events=tuple(
                _rollback_retention_event(deployment_id=deployment_id, published_at=published_at)
                for deployment_id, published_at in (
                    (active_id, "2020-01-03 01:00:00.000"),
                    (missing_id, "2020-01-02 01:00:00.000"),
                    (usable_id, "2020-01-01 01:00:00.000"),
                )
            ),
        ),
        managed_table_state=InspectedManagedTableState(
            active_bindings=(
                InspectedActiveTableBinding(
                    database="analytics",
                    logical_name="orders",
                    physical_name=f"orders__{active_id}",
                ),
            ),
            physical_candidates=tuple(
                InspectedPhysicalTableCandidate(
                    database="analytics",
                    logical_name=logical_name,
                    physical_name=f"{logical_name}__{deployment_id}",
                )
                for logical_name, deployment_id in (
                    ("orders", active_id),
                    ("mv__orders", active_id),
                    ("orders", missing_id),
                    ("orders", usable_id),
                    ("mv__orders", usable_id),
                )
            ),
        ),
        request=JanitorRequest(
            database="analytics",
            metadata_database="metadata",
            retention_days=0,
            apply=False,
            minimum_rollback_deployments=1,
        ),
        missing_deployment_id=missing_id,
        usable_deployment_id=usable_id,
        expected_usable_reason="retained as rollback point (minimum 1 deployments)",
    )


def catalog_relations_for_managed_state(
    managed_table_state: InspectedManagedTableState,
) -> tuple[CatalogRelation, ...]:
    return tuple(
        CatalogRelation(name=candidate.physical_name, engine="MergeTree", columns=())
        for candidate in managed_table_state.physical_candidates
    )


def _rollback_retention_deployment(
    *, deployment_id: str, created_at: str
) -> AdapterDeploymentRecord:
    return AdapterDeploymentRecord(
        deployment_id=deployment_id,
        created_at=created_at,
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
                physical_name=f"orders__{deployment_id}",
                logical_model_name="orders",
            ),
            AdapterPreparedObjectMapping(
                logical_key=AdapterMetadataObjectKey(
                    database=None,
                    object_type="materialized_view",
                    name="mv__orders",
                ),
                physical_name=f"mv__orders__{deployment_id}",
                logical_model_name="orders",
            ),
        ),
    )


def _rollback_retention_event(
    *, deployment_id: str, published_at: str
) -> AdapterPublishEventRecord:
    return AdapterPublishEventRecord(
        deployment_id=deployment_id,
        published_at=published_at,
        logical_view_names=("orders",),
        bindings=(
            AdapterStableBinding(
                database="analytics",
                logical_name="orders",
                physical_name=f"orders__{deployment_id}",
            ),
        ),
    )
