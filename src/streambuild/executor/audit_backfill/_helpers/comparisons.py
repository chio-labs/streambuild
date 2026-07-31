"""Build audit decisions from adapter readiness observations."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterReadinessOffsetSummary,
    AdapterReadinessRequest,
    AdapterReadinessRootObservation,
    AdapterReadinessRootRequest,
    AdapterReadinessScalarSummary,
    InspectedManagedTableState,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.compiler.compile.constants import DESIRED_OBJECT_TYPE_TABLE
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.types import RootDeploymentStateKind
from streambuild.executor.audit_backfill.constants import (
    ACCEPTABLE_LAG_SECONDS,
    MINIMUM_STAGED_ROW_RATIO,
)
from streambuild.executor.audit_backfill.models import (
    OffsetCatchupSummary,
    RootAuditResult,
    ScalarCatchupSummary,
)
from streambuild.executor.audit_backfill.types import AuditAssessment


def build_root_audit_results(
    *,
    client: AdapterConnection,
    default_database: str,
    inspected_state: InspectedManagedTableState,
    root_keys: tuple[ObjectKey, ...],
    prepared_object_mappings: tuple[tuple[ObjectKey, str], ...],
) -> tuple[RootAuditResult, ...]:
    """Build audit decisions for each adapter-observed staged root."""

    physical_name_by_key: dict[ObjectKey, str] = dict(prepared_object_mappings)
    staged_name_by_root: dict[ObjectKey, str] = {
        root_key: physical_name_by_key[root_key]
        for root_key in root_keys
        if root_key.object_type == DESIRED_OBJECT_TYPE_TABLE
        if root_key in physical_name_by_key
    }
    ordered_root_keys: tuple[ObjectKey, ...] = tuple(
        sorted(
            staged_name_by_root,
            key=lambda value: (value.database or "", value.object_type, value.name),
        )
    )
    root_requests: tuple[AdapterReadinessRootRequest, ...] = tuple(
        AdapterReadinessRootRequest(
            database=root_key.database or default_database,
            logical_name=root_key.name,
            staged_relation_name=staged_name_by_root[root_key],
            active_exists=_has_active_binding(
                inspected_state=inspected_state,
                root_key=root_key,
            ),
        )
        for root_key in ordered_root_keys
    )
    observations: tuple[AdapterReadinessRootObservation, ...] = client.compare_readiness(
        AdapterReadinessRequest(roots=root_requests)
    )
    observation_by_root: dict[AdapterReadinessRootRequest, AdapterReadinessRootObservation] = (
        _index_observations(root_requests=root_requests, observations=observations)
    )
    return tuple(
        _build_root_audit_result(
            root_key=root_key,
            root_request=root_request,
            observation=observation_by_root[root_request],
        )
        for root_key, root_request in zip(
            ordered_root_keys,
            root_requests,
            strict=True,
        )
    )


def _index_observations(
    *,
    root_requests: tuple[AdapterReadinessRootRequest, ...],
    observations: tuple[AdapterReadinessRootObservation, ...],
) -> dict[AdapterReadinessRootRequest, AdapterReadinessRootObservation]:
    observation_by_root: dict[AdapterReadinessRootRequest, AdapterReadinessRootObservation] = {
        observation.root: observation for observation in observations
    }
    if len(observation_by_root) != len(observations):
        raise AdapterResultError("Adapter readiness returned duplicate root observations")
    if set(observation_by_root) != set(root_requests):
        raise AdapterResultError("Adapter readiness observations did not match requested roots")
    return observation_by_root


def _build_root_audit_result(
    *,
    root_key: ObjectKey,
    root_request: AdapterReadinessRootRequest,
    observation: AdapterReadinessRootObservation,
) -> RootAuditResult:
    row_delta: int | None = None
    row_ratio: float | None = None
    if observation.active_row_count is not None and observation.staged_row_count is not None:
        row_delta = observation.staged_row_count - observation.active_row_count
        row_ratio = (
            None
            if observation.active_row_count == 0
            else observation.staged_row_count / observation.active_row_count
        )
    replay_lineage_mode: ReplayLineageMode | None = _replay_lineage_mode(
        observation.replay_boundary_mode
    )
    offset_summary: OffsetCatchupSummary | None = _offset_summary(observation.offset_summary)
    scalar_summary: ScalarCatchupSummary | None = _scalar_summary(observation.scalar_summary)
    warnings: tuple[str, ...] = _build_root_warnings(
        root_key=root_key,
        active_exists=root_request.active_exists,
        active_row_count=observation.active_row_count,
        staged_row_count=observation.staged_row_count,
        row_ratio=row_ratio,
        replay_source_name=observation.replay_source_name,
        replay_source_row_count=observation.replay_source_row_count,
    )
    return RootAuditResult(
        root_key=root_key,
        staged_physical_name=root_request.staged_relation_name,
        state=(
            RootDeploymentStateKind.ACTIVE_VIEW_PRESENT
            if root_request.active_exists
            else RootDeploymentStateKind.GREENFIELD
        ),
        replay_source_name=observation.replay_source_name,
        replay_source_row_count=observation.replay_source_row_count,
        staged_exists=observation.staged_exists,
        active_exists=root_request.active_exists,
        active_row_count=observation.active_row_count,
        staged_row_count=observation.staged_row_count,
        row_delta=row_delta,
        row_ratio=row_ratio,
        assessment=_build_root_assessment(
            staged_exists=observation.staged_exists,
            active_exists=root_request.active_exists,
            active_row_count=observation.active_row_count,
            staged_row_count=observation.staged_row_count,
            replay_lineage_mode=replay_lineage_mode,
            offset_summary=offset_summary,
            scalar_summary=scalar_summary,
        ),
        replay_lineage_mode=replay_lineage_mode,
        offset_catchup_summary=offset_summary,
        scalar_catchup_summary=scalar_summary,
        warnings=warnings,
    )


def _has_active_binding(
    *, inspected_state: InspectedManagedTableState, root_key: ObjectKey
) -> bool:
    return any(
        binding.database == (root_key.database or binding.database)
        and binding.logical_name == root_key.name
        for binding in inspected_state.active_bindings
    )


def _replay_lineage_mode(
    boundary_mode: AdapterReplayBoundaryMode | None,
) -> ReplayLineageMode | None:
    return None if boundary_mode is None else ReplayLineageMode(boundary_mode)


def _offset_summary(
    summary: AdapterReadinessOffsetSummary | None,
) -> OffsetCatchupSummary | None:
    if summary is None:
        return None
    return OffsetCatchupSummary(
        active_partition_count=summary.active_partition_count,
        staged_partition_count=summary.staged_partition_count,
        partitions_compared=summary.partitions_compared,
        missing_staged_partition_count=summary.missing_staged_partition_count,
        missing_freshness_partition_count=summary.missing_freshness_partition_count,
        lagging_partition_count=summary.lagging_partition_count,
        max_offset_gap=summary.max_offset_gap,
        average_offset_gap=summary.average_offset_gap,
        lag_boundary_column=summary.lag_boundary_column,
        max_lag_seconds=summary.max_lag_seconds,
        average_lag_seconds=summary.average_lag_seconds,
    )


def _scalar_summary(
    summary: AdapterReadinessScalarSummary | None,
) -> ScalarCatchupSummary | None:
    if summary is None:
        return None
    return ScalarCatchupSummary(
        active_min_value=summary.active_min_value,
        active_max_value=summary.active_max_value,
        staged_min_value=summary.staged_min_value,
        staged_max_value=summary.staged_max_value,
        lag_seconds=summary.lag_seconds,
    )


def _build_root_assessment(
    *,
    staged_exists: bool,
    active_exists: bool,
    active_row_count: int | None,
    staged_row_count: int | None,
    replay_lineage_mode: ReplayLineageMode | None,
    offset_summary: OffsetCatchupSummary | None,
    scalar_summary: ScalarCatchupSummary | None,
) -> AuditAssessment:
    if not staged_exists:
        return AuditAssessment.CAUTION
    if staged_row_count == 0:
        if active_exists and active_row_count is not None and active_row_count > 0:
            return AuditAssessment.NOT_READY
        return AuditAssessment.CAUTION
    if not active_exists:
        return AuditAssessment.READY
    if replay_lineage_mode == ReplayLineageMode.OFFSETS:
        return _offset_assessment(
            active_exists=active_exists,
            active_row_count=active_row_count,
            staged_row_count=staged_row_count,
            offset_summary=offset_summary,
        )
    if scalar_summary is None or scalar_summary.lag_seconds is None:
        return AuditAssessment.CAUTION
    if scalar_summary.lag_seconds > ACCEPTABLE_LAG_SECONDS:
        return AuditAssessment.NOT_READY
    return _row_ratio_assessment(
        active_row_count=active_row_count,
        staged_row_count=staged_row_count,
    )


def _offset_assessment(
    *,
    active_exists: bool,
    active_row_count: int | None,
    staged_row_count: int | None,
    offset_summary: OffsetCatchupSummary | None,
) -> AuditAssessment:
    if offset_summary is None:
        return AuditAssessment.CAUTION
    if active_exists and offset_summary.partitions_compared < offset_summary.active_partition_count:
        return AuditAssessment.CAUTION
    if active_exists and offset_summary.missing_staged_partition_count > 0:
        return AuditAssessment.CAUTION
    if offset_summary.missing_freshness_partition_count > 0:
        return AuditAssessment.CAUTION
    if offset_summary.lag_boundary_column is None or offset_summary.max_lag_seconds is None:
        return AuditAssessment.CAUTION
    if offset_summary.max_lag_seconds > ACCEPTABLE_LAG_SECONDS:
        return AuditAssessment.NOT_READY
    return _row_ratio_assessment(
        active_row_count=active_row_count,
        staged_row_count=staged_row_count,
    )


def _row_ratio_assessment(
    *, active_row_count: int | None, staged_row_count: int | None
) -> AuditAssessment:
    if (
        active_row_count is not None
        and staged_row_count is not None
        and active_row_count > 0
        and staged_row_count < active_row_count * MINIMUM_STAGED_ROW_RATIO
    ):
        return AuditAssessment.CAUTION
    return AuditAssessment.READY


def _build_root_warnings(
    *,
    root_key: ObjectKey,
    active_exists: bool,
    active_row_count: int | None,
    staged_row_count: int | None,
    row_ratio: float | None,
    replay_source_name: str | None,
    replay_source_row_count: int | None,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if replay_source_name is not None and replay_source_row_count == 0:
        warnings.append(f"replay source {replay_source_name} is empty")
    if (
        active_exists
        and active_row_count is not None
        and staged_row_count is not None
        and row_ratio is not None
        and row_ratio < MINIMUM_STAGED_ROW_RATIO
    ):
        warnings.append(f"staged row count is far below active row count for {root_key.name}")
    return tuple(warnings)
