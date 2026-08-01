"""Build one deterministic direct-mode plan for a selected downstream closure."""

from __future__ import annotations

from streambuild.adapter.models import (
    AdapterMaterializedView,
    AdapterOwnershipRecord,
    AdapterReplayColumns,
    AdapterTable,
    AdapterView,
)
from streambuild.adapter.types import AdapterOwningMode
from streambuild.compiler.compile.constants import (
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledPipeline,
    CompiledTableModel,
    ExternalSourceReplayConfig,
    LogicalResourceKey,
)
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.graph.constants import ALL_DEPENDENCY_EDGE_TYPES
from streambuild.compiler.graph.main.collect_reachable_keys import collect_reachable_keys
from streambuild.compiler.graph.models import DependencyEdge, ProjectGraph
from streambuild.compiler.graph.types import DependencyEdgeType, GraphTraversalDirection
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner._helpers.direct_ownership import classify_relation_ownership
from streambuild.compiler.planner.exceptions import DirectPlanError
from streambuild.compiler.planner.models import (
    DirectPlan,
    DirectPlanEntry,
    DirectPrerequisite,
    DirectRelationOperation,
    DirectReplayRoot,
    DirectWarehouseSnapshot,
    PlannerWarning,
)
from streambuild.compiler.planner.types import (
    DirectPlanReason,
    DirectRelationAction,
    DirectResourceKind,
    TargetOwnership,
)

_BLOCKING_OWNERSHIP: frozenset[TargetOwnership] = frozenset(
    {TargetOwnership.UNMANAGED, TargetOwnership.VIRTUAL_ENVIRONMENT, TargetOwnership.CONFLICTED}
)
_CANONICAL_REPLAY_COLUMNS: AdapterReplayColumns = AdapterReplayColumns(
    partition=REPLAY_PARTITION_COLUMN_NAME,
    offset=REPLAY_OFFSET_COLUMN_NAME,
    timestamp=REPLAY_TIMESTAMP_COLUMN_NAME,
    landed_at=REPLAY_LANDED_AT_COLUMN_NAME,
    cursor=REPLAY_CURSOR_COLUMN_NAME,
)


class DirectPlanBuilder:
    """Resolve scope, ownership, replay roots, and relation actions for one plan."""

    def __init__(
        self,
        *,
        graph: ProjectGraph,
        realized_project: RealizedProject,
        snapshot: DirectWarehouseSnapshot,
        database: str,
        selected_model_keys: frozenset[LogicalResourceKey],
    ) -> None:
        self._graph: ProjectGraph = graph
        self._realized_project: RealizedProject = realized_project
        self._snapshot: DirectWarehouseSnapshot = snapshot
        self._database: str = database
        self._selected_model_keys: frozenset[LogicalResourceKey] = selected_model_keys
        self._model_by_key: dict[LogicalResourceKey, CompiledModel] = {
            model.key: model for model in realized_project.project.models
        }
        self._execution_scope: tuple[LogicalResourceKey, ...] = self._resolve_execution_scope()
        self._executed_keys: frozenset[LogicalResourceKey] = frozenset(self._execution_scope)
        self._driving_parent_by_key: dict[LogicalResourceKey, LogicalResourceKey] = (
            self._resolve_driving_parents()
        )
        self._replay_lineage_mode_by_key: dict[LogicalResourceKey, ReplayLineageMode] = (
            _replay_lineage_modes_by_key(realized_project=realized_project)
        )
        self._aggregate_model_keys: frozenset[LogicalResourceKey] = frozenset(
            model.key
            for model in realized_project.project.models
            if isinstance(model, CompiledTableModel) and model.has_aggregate_semantics
        )
        self._external_config_by_relation_name: dict[str, ExternalSourceReplayConfig] = {
            config.table_name: config
            for config in realized_project.desired_state.external_source_replay_configs
        }

    def build(self) -> DirectPlan:
        """Return the complete execution closure without consulting equality."""

        self._reject_adopted_source_target_collisions()
        prerequisites: tuple[DirectPrerequisite, ...] = self._build_prerequisites()
        self._reject_missing_prerequisites(prerequisites=prerequisites)
        entries: tuple[DirectPlanEntry, ...] = self._build_entries()
        self._reject_blocked_ownership(entries=entries)
        stale_teardown_operations: tuple[DirectRelationOperation, ...] = (
            self._stale_teardown_operations(entries=entries)
        )
        return DirectPlan(
            database=self._database,
            user_scope=tuple(
                key for key in self._execution_scope if key in self._selected_model_keys
            ),
            execution_scope=self._execution_scope,
            prerequisite_scope=prerequisites,
            entries=entries,
            replay_roots=self._build_replay_roots(),
            teardown_operations=_teardown_operations(
                entries=entries,
                stale_operations=stale_teardown_operations,
            ),
            creation_operations=_creation_operations(entries=entries),
            warnings=self._build_warnings(entries=entries),
        )

    def _resolve_execution_scope(self) -> tuple[LogicalResourceKey, ...]:
        if not self._selected_model_keys:
            return _model_keys(keys=self._graph.ordered_keys)
        return _model_keys(
            keys=collect_reachable_keys(
                graph=self._graph,
                root_keys=self._selected_model_keys,
                direction=GraphTraversalDirection.DOWNSTREAM,
                edge_types=ALL_DEPENDENCY_EDGE_TYPES,
            )
        )

    def _resolve_driving_parents(self) -> dict[LogicalResourceKey, LogicalResourceKey]:
        driving_parent_by_key: dict[LogicalResourceKey, LogicalResourceKey] = {}
        key: LogicalResourceKey
        for key in self._graph.ordered_keys:
            edge: DependencyEdge
            for edge in self._graph.upstream_edges_by_key.get(key, ()):
                if edge.edge_type == DependencyEdgeType.DRIVING_INPUT:
                    driving_parent_by_key[key] = edge.upstream_key
        return driving_parent_by_key

    def _build_entries(self) -> tuple[DirectPlanEntry, ...]:
        return tuple(self._build_entry(model_key=model_key) for model_key in self._execution_scope)

    def _build_entry(self, *, model_key: LogicalResourceKey) -> DirectPlanEntry:
        model: CompiledModel = self._model_by_key[model_key]
        driving_parent_key: LogicalResourceKey | None = self._driving_parent_by_key.get(model_key)
        relations: tuple[tuple[str, DirectResourceKind], ...] = self._model_relations(
            model_key=model_key
        )
        if isinstance(model, CompiledTableModel) and driving_parent_key is None:
            driving_parent_key = self._require_driving_parent(model_key=model_key)
        relation_names: tuple[str, ...] = tuple(name for name, _kind in relations)
        return DirectPlanEntry(
            model_key=model_key,
            reason=self._plan_reason(model_key=model_key),
            relation_names=relation_names,
            resource_kinds=tuple(kind for _name, kind in relations),
            ownership=classify_relation_ownership(
                snapshot=self._snapshot, relation_names=relation_names
            ),
            driving_input_key=driving_parent_key,
            is_replay_root=(
                isinstance(model, CompiledTableModel)
                and driving_parent_key not in self._executed_keys
            ),
        )

    def _plan_reason(self, *, model_key: LogicalResourceKey) -> DirectPlanReason:
        if not self._selected_model_keys:
            return DirectPlanReason.ALL_MODELS
        if model_key in self._selected_model_keys:
            return DirectPlanReason.SELECTED
        return DirectPlanReason.DOWNSTREAM_OF_SELECTED

    def _build_prerequisites(self) -> tuple[DirectPrerequisite, ...]:
        existing_names: frozenset[str] = self._snapshot.catalog.relation_names()
        return tuple(
            DirectPrerequisite(
                key=prerequisite_key,
                relation_names=(self._relation_name(key=prerequisite_key),),
                present=self._relation_name(key=prerequisite_key) in existing_names,
                framework_managed=self._is_framework_managed_source(key=prerequisite_key),
            )
            for prerequisite_key in self._prerequisite_keys()
        )

    def _is_framework_managed_source(self, *, key: LogicalResourceKey) -> bool:
        if key.resource_type != LogicalResourceType.SOURCE:
            return False
        return bool(self._realized_project.resources_by_logical_key[key])

    def _prerequisite_keys(self) -> tuple[LogicalResourceKey, ...]:
        prerequisite_keys: set[LogicalResourceKey] = set()
        model_key: LogicalResourceKey
        for model_key in self._execution_scope:
            edge: DependencyEdge
            for edge in self._graph.upstream_edges_by_key.get(model_key, ()):
                if edge.upstream_key not in self._executed_keys:
                    prerequisite_keys.add(edge.upstream_key)
        return tuple(key for key in self._graph.ordered_keys if key in prerequisite_keys)

    def _build_replay_roots(self) -> tuple[DirectReplayRoot, ...]:
        propagated_by_root: dict[LogicalResourceKey, list[LogicalResourceKey]] = {}
        model_key: LogicalResourceKey
        for model_key in self._execution_scope:
            if not isinstance(self._model_by_key[model_key], CompiledTableModel):
                continue
            root_key: LogicalResourceKey = self._replay_root_key(model_key=model_key)
            propagated_by_root.setdefault(root_key, []).append(model_key)
        root_key: LogicalResourceKey
        return tuple(
            self._build_replay_root(
                root_key=root_key, propagated_model_keys=tuple(propagated_by_root[root_key])
            )
            for root_key in self._execution_scope
            if root_key in propagated_by_root
        )

    def _build_replay_root(
        self,
        *,
        root_key: LogicalResourceKey,
        propagated_model_keys: tuple[LogicalResourceKey, ...],
    ) -> DirectReplayRoot:
        driving_input_key: LogicalResourceKey = self._require_driving_parent(model_key=root_key)
        return DirectReplayRoot(
            model_key=root_key,
            driving_input_key=driving_input_key,
            driving_input_relation_name=self._relation_name(key=driving_input_key),
            driving_input_replay_columns=self._driving_input_replay_columns(
                driving_input_key=driving_input_key
            ),
            replay_boundary_mode=self._replay_boundary_mode(model_key=root_key),
            propagated_model_keys=propagated_model_keys,
            has_aggregate_semantics=root_key in self._aggregate_model_keys,
        )

    def _reject_adopted_source_target_collisions(self) -> None:
        target_names: set[str] = set()
        model_key: LogicalResourceKey
        for model_key in self._execution_scope:
            target_names.update(name for name, _kind in self._model_relations(model_key=model_key))
        collisions: tuple[str, ...] = tuple(
            sorted(target_names & self._external_config_by_relation_name.keys())
        )
        if collisions:
            raise DirectPlanError(
                "Direct mode refuses adopted source relations that collide with managed "
                f"targets: {', '.join(collisions)}"
            )

    def _driving_input_replay_columns(
        self, *, driving_input_key: LogicalResourceKey
    ) -> AdapterReplayColumns:
        if driving_input_key.resource_type != LogicalResourceType.SOURCE:
            return _CANONICAL_REPLAY_COLUMNS
        relation_name: str = self._relation_name(key=driving_input_key)
        config: ExternalSourceReplayConfig | None = self._external_config_by_relation_name.get(
            relation_name
        )
        if config is None:
            return _CANONICAL_REPLAY_COLUMNS
        return AdapterReplayColumns(
            partition=config.partition_column_name or REPLAY_PARTITION_COLUMN_NAME,
            offset=config.offset_column_name or REPLAY_OFFSET_COLUMN_NAME,
            timestamp=config.timestamp_column_name or REPLAY_TIMESTAMP_COLUMN_NAME,
            landed_at=(
                config.landed_at_column_name
                or config.timestamp_column_name
                or REPLAY_LANDED_AT_COLUMN_NAME
            ),
            cursor=config.cursor_column_name or REPLAY_CURSOR_COLUMN_NAME,
        )

    def _build_warnings(
        self, *, entries: tuple[DirectPlanEntry, ...]
    ) -> tuple[PlannerWarning, ...]:
        target_names: set[str] = set()
        entry: DirectPlanEntry
        for entry in entries:
            relation_name: str
            resource_kind: DirectResourceKind
            for relation_name, resource_kind in zip(
                entry.relation_names, entry.resource_kinds, strict=True
            ):
                if resource_kind == DirectResourceKind.TABLE:
                    target_names.add(relation_name)
        return tuple(
            PlannerWarning(
                warning_code="mutable_ref_replay_not_guaranteed",
                message=(
                    "Transform uses mutable side refs; exact historical replay equivalence "
                    "cannot be guaranteed because side-table state may differ from the original "
                    "processing time."
                ),
                root_key=key,
                target_key=key,
            )
            for key in sorted(
                self._realized_project.desired_state.mutable_ref_warning_keys,
                key=lambda candidate: candidate.name,
            )
            if key.name in target_names
        )

    def _replay_root_key(self, *, model_key: LogicalResourceKey) -> LogicalResourceKey:
        current_key: LogicalResourceKey = model_key
        while True:
            parent_key: LogicalResourceKey | None = self._driving_parent_by_key.get(current_key)
            if parent_key is None or parent_key not in self._executed_keys:
                return current_key
            current_key = parent_key

    def _replay_boundary_mode(self, *, model_key: LogicalResourceKey) -> ReplayLineageMode:
        replay_lineage_mode: ReplayLineageMode | None = self._replay_lineage_mode_by_key.get(
            model_key
        )
        if replay_lineage_mode is None:
            raise DirectPlanError(
                f"Direct plan cannot resolve the replay mode of '{model_key.name}'"
            )
        return replay_lineage_mode

    def _relation_name(self, *, key: LogicalResourceKey) -> str:
        return self._realized_project.relation_name_by_logical_key[key]

    def _model_relations(
        self, *, model_key: LogicalResourceKey
    ) -> tuple[tuple[str, DirectResourceKind], ...]:
        resources: tuple[object, ...] = self._realized_project.resources_by_logical_key[model_key]
        table_names: tuple[str, ...] = tuple(
            resource.name for resource in resources if isinstance(resource, AdapterTable)
        )
        view_names: tuple[str, ...] = tuple(
            resource.name for resource in resources if isinstance(resource, AdapterMaterializedView)
        )
        ordinary_view_names: tuple[str, ...] = tuple(
            resource.name for resource in resources if isinstance(resource, AdapterView)
        )
        if len(ordinary_view_names) == 1 and not table_names and not view_names:
            return ((ordinary_view_names[0], DirectResourceKind.VIEW),)
        if len(table_names) != 1 or len(view_names) != 1 or ordinary_view_names:
            raise DirectPlanError(
                f"Direct plan received invalid realized resources for '{model_key.name}'"
            )
        return (
            (table_names[0], DirectResourceKind.TABLE),
            (view_names[0], DirectResourceKind.MATERIALIZED_VIEW),
        )

    def _require_driving_parent(self, *, model_key: LogicalResourceKey) -> LogicalResourceKey:
        driving_parent_key: LogicalResourceKey | None = self._driving_parent_by_key.get(model_key)
        if driving_parent_key is None:
            raise DirectPlanError(
                f"Direct plan cannot find the driving input of model '{model_key.name}'"
            )
        return driving_parent_key

    def _reject_missing_prerequisites(
        self, *, prerequisites: tuple[DirectPrerequisite, ...]
    ) -> None:
        missing_names: tuple[str, ...] = tuple(
            prerequisite.relation_names[0]
            for prerequisite in prerequisites
            if not prerequisite.present and not prerequisite.framework_managed
        )
        if missing_names:
            raise DirectPlanError(
                "Direct plan requires preserved upstream relations that do not exist: "
                f"{', '.join(missing_names)}"
            )

    def _reject_blocked_ownership(self, *, entries: tuple[DirectPlanEntry, ...]) -> None:
        blocked: list[str] = []
        entry: DirectPlanEntry
        for entry in entries:
            blocked.extend(_blocked_ownership_details(entry=entry))
        if blocked:
            raise DirectPlanError(
                f"Direct mode refuses to replace relations it does not own: {'; '.join(blocked)}"
            )

    def _stale_teardown_operations(
        self, *, entries: tuple[DirectPlanEntry, ...]
    ) -> tuple[DirectRelationOperation, ...]:
        entry_by_model_name: dict[str, DirectPlanEntry] = {
            entry.model_key.name: entry for entry in entries
        }
        current_relation_names: frozenset[str] = _entry_relation_names(entries=entries)
        operations: list[DirectRelationOperation] = []
        record: AdapterOwnershipRecord
        for record in self._snapshot.ownership_records:
            entry: DirectPlanEntry | None = entry_by_model_name.get(record.logical_model_name)
            if (
                entry is None
                or record.database_name != self._database
                or record.owning_mode != AdapterOwningMode.DIRECT
                or record.relation_name in current_relation_names
            ):
                continue
            operations.append(
                DirectRelationOperation(
                    relation_name=record.relation_name,
                    action=DirectRelationAction.DROP,
                    model_key=entry.model_key,
                    resource_kind=record.resource_kind,
                )
            )
        return tuple(operations)


def _blocked_ownership_details(*, entry: DirectPlanEntry) -> tuple[str, ...]:
    return tuple(
        f"{classification.relation_name} is {classification.ownership}"
        for classification in entry.ownership
        if classification.ownership in _BLOCKING_OWNERSHIP
    )


def _entry_relation_names(*, entries: tuple[DirectPlanEntry, ...]) -> frozenset[str]:
    relation_names: set[str] = set()
    for entry in entries:
        relation_names.update(entry.relation_names)
    return frozenset(relation_names)


def _teardown_operations(
    *,
    entries: tuple[DirectPlanEntry, ...],
    stale_operations: tuple[DirectRelationOperation, ...] = (),
) -> tuple[DirectRelationOperation, ...]:
    reversed_entries: tuple[DirectPlanEntry, ...] = tuple(reversed(entries))
    operations: list[DirectRelationOperation] = []
    resource_kind: DirectResourceKind
    for resource_kind in (
        DirectResourceKind.VIEW,
        DirectResourceKind.MATERIALIZED_VIEW,
        DirectResourceKind.TABLE,
    ):
        operations.extend(
            _relation_operations(
                entries=reversed_entries,
                action=DirectRelationAction.DROP,
                resource_kind=resource_kind,
            )
        )
        operations.extend(
            operation for operation in stale_operations if operation.resource_kind == resource_kind
        )
    return tuple(operations)


def _creation_operations(
    *, entries: tuple[DirectPlanEntry, ...]
) -> tuple[DirectRelationOperation, ...]:
    operations: list[DirectRelationOperation] = []
    resource_kind: DirectResourceKind
    for resource_kind in (
        DirectResourceKind.TABLE,
        DirectResourceKind.MATERIALIZED_VIEW,
        DirectResourceKind.VIEW,
    ):
        operations.extend(
            _relation_operations(
                entries=entries,
                action=DirectRelationAction.CREATE,
                resource_kind=resource_kind,
            )
        )
    return tuple(operations)


def _relation_operations(
    *,
    entries: tuple[DirectPlanEntry, ...],
    action: DirectRelationAction,
    resource_kind: DirectResourceKind,
) -> tuple[DirectRelationOperation, ...]:
    operations: list[DirectRelationOperation] = []
    entry: DirectPlanEntry
    for entry in entries:
        relation_name: str
        relation_kind: DirectResourceKind
        for relation_name, relation_kind in zip(
            entry.relation_names, entry.resource_kinds, strict=True
        ):
            if relation_kind == resource_kind:
                operations.append(
                    DirectRelationOperation(
                        relation_name=relation_name,
                        action=action,
                        model_key=entry.model_key,
                        resource_kind=relation_kind,
                    )
                )
    return tuple(operations)


def _replay_lineage_modes_by_key(
    *, realized_project: RealizedProject
) -> dict[LogicalResourceKey, ReplayLineageMode]:
    replay_lineage_mode_by_key: dict[LogicalResourceKey, ReplayLineageMode] = {}
    pipeline: CompiledPipeline
    for pipeline in realized_project.project.pipelines:
        if pipeline.source is None or pipeline.effective_replay_lineage_mode is None:
            continue
        replay_lineage_mode_by_key[pipeline.source.key] = pipeline.effective_replay_lineage_mode
        model: CompiledModel
        for model in pipeline.models:
            replay_lineage_mode_by_key[model.key] = pipeline.effective_replay_lineage_mode
    return replay_lineage_mode_by_key


def _model_keys(*, keys: tuple[LogicalResourceKey, ...]) -> tuple[LogicalResourceKey, ...]:
    return tuple(key for key in keys if key.resource_type == LogicalResourceType.MODEL)
