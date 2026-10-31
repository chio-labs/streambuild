"""Publish the exact live-binding effects of a deployment promotion."""

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.adapter.models import InspectedManagedTableState
from sqltide.executor.promotion._helpers.views import (
    build_binding_replacement_preview,
    build_publish_binding_request,
)
from sqltide.executor.promotion.models import DeploymentPromotionPreview


def build_deployment_promotion_preview(
    *,
    client: AdapterConnection,
    metadata_database: str,
    default_database: str,
    deployment_id: str,
    inspected_state: InspectedManagedTableState,
) -> DeploymentPromotionPreview:
    """Return promotion effects from the same binding request execution uses."""

    return build_binding_replacement_preview(
        binding_request=build_publish_binding_request(
            client=client,
            metadata_database=metadata_database,
            default_database=default_database,
            deployment_id=deployment_id,
            inspected_state=inspected_state,
        ),
        active_bindings=inspected_state.active_bindings,
    )
