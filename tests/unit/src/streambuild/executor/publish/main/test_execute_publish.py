import pytest

from streambuild.adapter.exceptions import AdapterCapabilityError, AdapterResultError
from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterMetadataObjectKey,
    AdapterPreparedObjectMapping,
    AdapterStableBinding,
    CatalogRelation,
    InspectedManagedTableState,
    InspectedPhysicalTableCandidate,
)
from streambuild.executor.publish.main.execute_publish import execute_publish
from streambuild.executor.publish.models import PublishRequest
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.executor.publish.main._test_types import (
    PublishCapabilityRejectionTestCase,
)
from tests.unit.src.streambuild.executor.publish.main.helpers import (
    WrongBindingAdapterConnection,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PublishCapabilityRejectionTestCase(
            description="rejects publish before inspection when stable bindings are unsupported",
            expected_error_fragment=(
                "Adapter 'clickhouse' does not support stable logical bindings"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_without_stable_bindings_when_publishing_then_it_fails_before_writes(
    test_case: PublishCapabilityRejectionTestCase,
) -> None:
    connection: RecordingAdapterConnection = RecordingAdapterConnection(
        stable_logical_bindings=False
    )

    with pytest.raises(AdapterCapabilityError, match=test_case.expected_error_fragment):
        execute_publish(
            request=PublishRequest(
                deployment_id="20260726T190000Z_ab12cd",
                metadata_database="analytics",
                default_database="analytics",
            ),
            client=connection,
        )

    assert connection.binding_requests == []
    assert connection.statements == []


@pytest.mark.parametrize(
    "test_case",
    [
        PublishCapabilityRejectionTestCase(
            description="rejects an adapter result with a different physical binding",
            expected_error_fragment=(
                "Adapter returned bindings that did not match the publish request"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_returns_wrong_binding_when_publishing_then_history_is_not_persisted(
    test_case: PublishCapabilityRejectionTestCase,
) -> None:
    deployment_id: str = "20260726T190000Z_ab12cd"
    connection: WrongBindingAdapterConnection = WrongBindingAdapterConnection(
        managed_table_state=InspectedManagedTableState(
            active_bindings=(),
            physical_candidates=(
                InspectedPhysicalTableCandidate(
                    database="analytics",
                    logical_name="tbl__orders_enriched",
                    physical_name=f"tbl__orders_enriched__{deployment_id}",
                ),
            ),
        ),
        deployment_inventory=AdapterDeploymentInventory(
            deployments=(
                AdapterDeploymentRecord(
                    deployment_id=deployment_id,
                    created_at="2026-07-26 19:00:00.000",
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
                            physical_name=f"tbl__orders_enriched__{deployment_id}",
                            logical_model_name="orders_enriched",
                        ),
                    ),
                ),
            ),
            publish_events=(),
        ),
        relations=(
            CatalogRelation(
                name=f"tbl__orders_enriched__{deployment_id}",
                engine="MergeTree",
                columns=(),
            ),
        ),
        returned_bindings=(
            AdapterStableBinding(
                database="analytics",
                logical_name="tbl__orders_enriched",
                physical_name="tbl__orders_enriched__wrong",
            ),
        ),
    )

    with pytest.raises(AdapterResultError, match=test_case.expected_error_fragment):
        execute_publish(
            request=PublishRequest(
                deployment_id=deployment_id,
                metadata_database="analytics",
                default_database="analytics",
            ),
            client=connection,
        )

    assert len(connection.binding_requests) == 1
    assert connection.persisted_metadata_states == []
