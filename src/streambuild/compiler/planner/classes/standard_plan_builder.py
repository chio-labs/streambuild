"""Build one deterministic standard-mode plan for a selected downstream closure."""

from __future__ import annotations

from streambuild.adapter.models import AdapterMaterializedView, AdapterTable
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledPipeline,
    LogicalResourceKey,
)
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.graph.constants import ALL_DEPENDENCY_EDGE_TYPES
from streambuild.compiler.graph.main.collect_reachable_keys import collect_reachable_keys
from streambuild.compiler.graph.models import DependencyEdge, ProjectGraph
from streambuild.compiler.graph.types import DependencyEdgeType, GraphTraversalDirection
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner._helpers.standard_ownership import classify_relation_ownership
from streambuild.compiler.planner.exceptions import StandardPlanError
from streambuild.compiler.planner.models import (
    StandardPlan,
    StandardPlanEntry,
    StandardPrerequisite,
    StandardRelationOperation,
    StandardReplayRoot,
    StandardWarehouseSnapshot,
)
from streambuild.compiler.planner.types import (
    StandardPlanReason,
    StandardRelationAction,
    TargetOwnership,
)

_BLOCKING_OWNERSHIP: frozenset[TargetOwnership] = frozenset(
    {TargetOwnership.UNMANAGED, TargetOwnership.VIRTUAL_ENVIRONMENT, TargetOwnership.CONFLICTED}
)
_TABLE_RELATION_INDEX: int = 0
_VIEW_RELATION_INDEX: int = 1


class StandardPlanBuilder:
    """Resolve scope, ownership, replay roots, and relation actions for one plan."""

    def __init__(
        self,
        *,
        graph: ProjectGraph,
        realized_project: RealizedProject,
        snapshot: StandardWarehouseSnapshot,
        database: str,
        selected_model_keys: frozenset[LogicalResourceKey],
    ) -> None:
        self._graph: ProjectGraph = graph
        self._realized_project: RealizedProject = realized_project
        self._snapshot: StandardWarehouseSnapshot = snapshot
        self._database: str = database
        self._selected_model_keys: frozenset[LogicalResourceKey] = selected_model_keys
        self._execution_scope: tuple[LogicalResourceKey, ...] = self._resolve_execution_scope()
        self._executed_keys: frozenset[LogicalResourceKey] = frozenset(self._execution_scope)
        self._driving_parent_by_key: dict[LogicalResourceKey, LogicalResourceKey] = (
            self._resolve_driving_parents()
        )
        self._replay_lineage_mode_by_key: dict[LogicalResourceKey, ReplayLineageMode] = (
            _replay_lineage_modes_by_key(realized_project=realized_project)
        )

    def build(self) -> StandardPlan:
        """Return the complete execution closure without consulting equality."""

        prerequisites: tuple[StandardPrerequisite, ...] = self._build_prerequisites()
        self._reject_missing_prerequisites(prerequisites=prerequisites)
        entries: tuple[StandardPlanEntry, ...] = self._build_entries()
        self._reject_blocked_ownership(entries=entries)
        return StandardPlan(
            database=self._database,
            user_scope=tuple(
                key for key in self._execution_scope if key in self._selected_model_keys
            ),
            execution_scope=self._execution_scope,
            prerequisite_scope=prerequisites,
            entries=entries,
            replay_roots=self._build_replay_roots(),
            teardown_operations=_teardown_operations(entries=entries),
            creation_operations=_creation_operations(entries=entries),
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

    def _build_entries(self) -> tuple[StandardPlanEntry, ...]:
        return tuple(self._build_entry(model_key=model_key) for model_key in self._execution_scope)

    def _build_entry(self, *, model_key: LogicalResourceKey) -> StandardPlanEntry:
        driving_parent_key: LogicalResourceKey = self._require_driving_parent(model_key=model_key)
        relation_names: tuple[str, ...] = self._model_relation_names(model_key=model_key)
        return StandardPlanEntry(
            model_key=model_key,
            reason=self._plan_reason(model_key=model_key),
            relation_names=relation_names,
            ownership=classify_relation_ownership(
                snapshot=self._snapshot, relation_names=relation_names
            ),
            driving_input_key=driving_parent_key,
            is_replay_root=driving_parent_key not in self._executed_keys,
        )

    def _plan_reason(self, *, model_key: LogicalResourceKey) -> StandardPlanReason:
        if not self._selected_model_keys:
            return StandardPlanReason.ALL_MODELS
        if model_key in self._selected_model_keys:
            return StandardPlanReason.SELECTED
        return StandardPlanReason.DOWNSTREAM_OF_SELECTED

    def _build_prerequisites(self) -> tuple[StandardPrerequisite, ...]:
        existing_names: frozenset[str] = self._snapshot.catalog.relation_names()
        return tuple(
            StandardPrerequisite(
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

    def _build_replay_roots(self) -> tuple[StandardReplayRoot, ...]:
        propagated_by_root: dict[LogicalResourceKey, list[LogicalResourceKey]] = {}
        model_key: LogicalResourceKey
        for model_key in self._execution_scope:
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
    ) -> StandardReplayRoot:
        driving_input_key: LogicalResourceKey = self._require_driving_parent(model_key=root_key)
        return StandardReplayRoot(
            model_key=root_key,
            driving_input_key=driving_input_key,
            driving_input_relation_name=self._relation_name(key=driving_input_key),
            replay_boundary_mode=self._replay_boundary_mode(model_key=root_key),
            propagated_model_keys=propagated_model_keys,
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
            raise StandardPlanError(
                f"Standard plan cannot resolve the replay mode of '{model_key.name}'"
            )
        return replay_lineage_mode

    def _relation_name(self, *, key: LogicalResourceKey) -> str:
        return self._realized_project.relation_name_by_logical_key[key]

    def _model_relation_names(self, *, model_key: LogicalResourceKey) -> tuple[str, ...]:
        resources: tuple[object, ...] = self._realized_project.resources_by_logical_key[model_key]
        table_names: tuple[str, ...] = tuple(
            resource.name for resource in resources if isinstance(resource, AdapterTable)
        )
        view_names: tuple[str, ...] = tuple(
            resource.name for resource in resources if isinstance(resource, AdapterMaterializedView)
        )
        if len(table_names) != 1 or len(view_names) != 1:
            raise StandardPlanError(
                f"Standard plan expects one table and one materialized view for '{model_key.name}'"
            )
        return (table_names[0], view_names[0])

    def _require_driving_parent(self, *, model_key: LogicalResourceKey) -> LogicalResourceKey:
        driving_parent_key: LogicalResourceKey | None = self._driving_parent_by_key.get(model_key)
        if driving_parent_key is None:
            raise StandardPlanError(
                f"Standard plan cannot find the driving input of model '{model_key.name}'"
            )
        return driving_parent_key

    def _reject_missing_prerequisites(
        self, *, prerequisites: tuple[StandardPrerequisite, ...]
    ) -> None:
        missing_names: tuple[str, ...] = tuple(
            prerequisite.relation_names[0]
            for prerequisite in prerequisites
            if not prerequisite.present and not prerequisite.framework_managed
        )
        if missing_names:
            raise StandardPlanError(
                "Standard plan requires preserved upstream relations that do not exist: "
                f"{', '.join(missing_names)}"
            )

    def _reject_blocked_ownership(self, *, entries: tuple[StandardPlanEntry, ...]) -> None:
        blocked: list[str] = []
        entry: StandardPlanEntry
        for entry in entries:
            blocked.extend(_blocked_ownership_details(entry=entry))
        if blocked:
            raise StandardPlanError(
                f"Standard mode refuses to replace relations it does not own: {'; '.join(blocked)}"
            )


def _blocked_ownership_details(*, entry: StandardPlanEntry) -> tuple[str, ...]:
    return tuple(
        f"{classification.relation_name} is {classification.ownership}"
        for classification in entry.ownership
        if classification.ownership in _BLOCKING_OWNERSHIP
    )


def _teardown_operations(
    *, entries: tuple[StandardPlanEntry, ...]
) -> tuple[StandardRelationOperation, ...]:
    reversed_entries: tuple[StandardPlanEntry, ...] = tuple(reversed(entries))
    return (
        *_relation_operations(
            entries=reversed_entries,
            action=StandardRelationAction.DROP,
            index=_VIEW_RELATION_INDEX,
        ),
        *_relation_operations(
            entries=reversed_entries,
            action=StandardRelationAction.DROP,
            index=_TABLE_RELATION_INDEX,
        ),
    )


def _creation_operations(
    *, entries: tuple[StandardPlanEntry, ...]
) -> tuple[StandardRelationOperation, ...]:
    return (
        *_relation_operations(
            entries=entries, action=StandardRelationAction.CREATE, index=_TABLE_RELATION_INDEX
        ),
        *_relation_operations(
            entries=entries, action=StandardRelationAction.CREATE, index=_VIEW_RELATION_INDEX
        ),
    )


def _relation_operations(
    *, entries: tuple[StandardPlanEntry, ...], action: StandardRelationAction, index: int
) -> tuple[StandardRelationOperation, ...]:
    return tuple(
        StandardRelationOperation(
            relation_name=entry.relation_names[index],
            action=action,
            model_key=entry.model_key,
        )
        for entry in entries
    )


def _replay_lineage_modes_by_key(
    *, realized_project: RealizedProject
) -> dict[LogicalResourceKey, ReplayLineageMode]:
    replay_lineage_mode_by_key: dict[LogicalResourceKey, ReplayLineageMode] = {}
    pipeline: CompiledPipeline
    for pipeline in realized_project.project.pipelines:
        replay_lineage_mode_by_key[pipeline.source.key] = pipeline.effective_replay_lineage_mode
        model: CompiledModel
        for model in pipeline.models:
            replay_lineage_mode_by_key[model.key] = pipeline.effective_replay_lineage_mode
    return replay_lineage_mode_by_key


def _model_keys(*, keys: tuple[LogicalResourceKey, ...]) -> tuple[LogicalResourceKey, ...]:
    return tuple(key for key in keys if key.resource_type == LogicalResourceType.MODEL)
