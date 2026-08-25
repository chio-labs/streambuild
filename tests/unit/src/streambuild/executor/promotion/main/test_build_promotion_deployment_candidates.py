import pytest

from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterMetadataObjectKey,
    AdapterPreparedObjectMapping,
    CatalogRelation,
    InspectedManagedTableState,
    InspectedPhysicalTableCandidate,
)
from streambuild.executor.promotion._helpers.views import (
    build_publish_binding_request,
)
from streambuild.executor.promotion.exceptions import PublishExecutionError
from streambuild.executor.promotion.main.build_promotion_deployment_candidates import (
    build_publish_deployment_candidates,
)
from streambuild.executor.readiness.models import AuditDeploymentCandidate
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.executor.promotion.main._test_types import (
    PromotionCandidateCompletenessTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PromotionCandidateCompletenessTestCase(
            description="partial deployment is excluded from candidates",
            partial_deployment_id="20260806T000100Z_partial",
            complete_deployment_id="20260806T000200Z_complete",
            expected_deployment_ids=("20260806T000200Z_complete",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_deployments_when_listing_candidates_then_only_complete_remains(
    test_case: PromotionCandidateCompletenessTestCase,
) -> None:
    partial_id: str = test_case.partial_deployment_id
    complete_id: str = test_case.complete_deployment_id
    partial: AdapterDeploymentRecord = AdapterDeploymentRecord(
        deployment_id=partial_id,
        created_at="2026-08-06 00:01:00.000",
        status="staged",
        replay_lineage_mode="offsets",
        selected_root_keys=(),
        warning_codes=(),
        prepared_object_mappings=(
            AdapterPreparedObjectMapping(
                logical_key=AdapterMetadataObjectKey(None, "table", "orders"),
                physical_name=f"orders__{partial_id}",
                logical_model_name="orders",
            ),
            AdapterPreparedObjectMapping(
                logical_key=AdapterMetadataObjectKey(None, "table", "prices"),
                physical_name=f"prices__{partial_id}",
                logical_model_name="prices",
            ),
            AdapterPreparedObjectMapping(
                logical_key=AdapterMetadataObjectKey(None, "materialized_view", "mv__prices"),
                physical_name=f"mv__prices__{partial_id}",
                logical_model_name="prices",
            ),
        ),
    )
    complete: AdapterDeploymentRecord = AdapterDeploymentRecord(
        deployment_id=complete_id,
        created_at="2026-08-06 00:02:00.000",
        status="staged",
        replay_lineage_mode="offsets",
        selected_root_keys=(),
        warning_codes=(),
        prepared_object_mappings=(
            AdapterPreparedObjectMapping(
                logical_key=AdapterMetadataObjectKey(None, "table", "orders"),
                physical_name=f"orders__{complete_id}",
                logical_model_name="orders",
            ),
            AdapterPreparedObjectMapping(
                logical_key=AdapterMetadataObjectKey(None, "table", "prices"),
                physical_name=f"prices__{complete_id}",
                logical_model_name="prices",
            ),
            AdapterPreparedObjectMapping(
                logical_key=AdapterMetadataObjectKey(None, "materialized_view", "mv__prices"),
                physical_name=f"mv__prices__{complete_id}",
                logical_model_name="prices",
            ),
        ),
    )
    connection: RecordingAdapterConnection = RecordingAdapterConnection(
        relations=tuple(
            CatalogRelation(name=name, engine="MergeTree", columns=())
            for name in (
                f"orders__{partial_id}",
                f"prices__{partial_id}",
                f"orders__{complete_id}",
                f"prices__{complete_id}",
                f"mv__prices__{complete_id}",
            )
        ),
        managed_table_state=InspectedManagedTableState(
            active_bindings=(),
            physical_candidates=tuple(
                InspectedPhysicalTableCandidate(
                    database="analytics",
                    logical_name=name,
                    physical_name=f"{name}__{partial_id}",
                )
                for name in ("orders", "prices")
            ),
        ),
        deployment_inventory=AdapterDeploymentInventory(
            deployments=(partial, complete),
            publish_events=(),
        ),
    )

    candidates: tuple[AuditDeploymentCandidate, ...] = build_publish_deployment_candidates(
        client=connection,
        metadata_database="metadata",
        default_database="analytics",
    )

    assert (
        tuple(candidate.deployment_id for candidate in candidates)
        == test_case.expected_deployment_ids
    )
    with pytest.raises(PublishExecutionError, match="missing staged relations"):
        build_publish_binding_request(
            client=connection,
            metadata_database="metadata",
            default_database="analytics",
            deployment_id=partial_id,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
