"""Persist population watermarks when a durable deployment requests it."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.planner.main.build_adapter_metadata_state import (
    build_adapter_metadata_state,
)
from streambuild.compiler.planner.main.build_metadata_state import build_metadata_state
from streambuild.compiler.planner.models import DeploymentWatermarkRecord, MetadataState
from streambuild.executor.population.models import PopulationPlan, PopulationWatermark


def persist_population_watermarks(
    *,
    client: AdapterConnection,
    metadata_database: str,
    plan: PopulationPlan,
    watermarks: tuple[PopulationWatermark, ...],
) -> None:
    """Persist inclusive cutoff rows before replay starts."""

    persisted_root_keys: frozenset[ObjectKey] = frozenset(
        root.root_key for root in plan.roots if root.persist_watermarks
    )
    records: tuple[DeploymentWatermarkRecord, ...] = tuple(
        DeploymentWatermarkRecord(
            deployment_id=plan.execution_id,
            root_key=watermark.root_key,
            anchor_key=watermark.anchor_key,
            boundary_key=watermark.boundary_key,
            cutoff_value=watermark.cutoff_value,
        )
        for watermark in watermarks
        if watermark.root_key in persisted_root_keys
    )
    metadata_state: MetadataState = build_metadata_state(
        object_states=(),
        deployments=(),
        deployment_watermarks=records,
        deployment_runtime_details=(),
        publish_events=(),
    )
    client.persist_metadata_state(
        database=metadata_database,
        state=build_adapter_metadata_state(metadata_state),
    )
