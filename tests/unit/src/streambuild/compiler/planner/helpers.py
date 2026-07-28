from collections.abc import Callable
from dataclasses import replace
from itertools import chain
from pathlib import Path
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterBindingReplacementResult,
    AdapterCapabilities,
    AdapterDeploymentInventory,
    AdapterIdentity,
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterMetadataState,
    AdapterOwnershipRecord,
    AdapterQueryResult,
    AdapterReadinessRequest,
    AdapterReadinessRootObservation,
    AdapterRelationCleanupRequest,
    AdapterRelationCleanupResult,
    AdapterReplayRequest,
    AdapterStableView,
    AdapterTable,
    CatalogColumn,
    CatalogIdentity,
    CatalogRelation,
    CatalogSnapshot,
    InspectedManagedTableState,
)
from streambuild.adapter.types import AdapterOwningMode, AdapterReplayBoundaryMode
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_KAFKA_TABLE,
    DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
    DESIRED_OBJECT_TYPE_TABLE,
)
from streambuild.compiler.compile.main._compile_pipeline import (
    compile_pipeline as compile_pipeline_impl,
)
from streambuild.compiler.compile.models import (
    Column,
    CompiledPipeline,
    CompiledProject,
    CompiledSource,
    CompilerAdapterProfile,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    KafkaTableSpec,
    LogicalResourceKey,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.compiler.compile.models import (
    KafkaSettings as CompiledKafkaSettings,
)
from streambuild.compiler.compile.types import DesiredObjectType
from streambuild.compiler.discovery._helpers.load import load_pipeline_file
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import (
    ExternalTableSourceStep,
    KafkaLandingStep,
    KafkaSettings,
    LoadedPipeline,
    Pipeline,
    ReplayBoundary,
    ReplayBoundaryColumns,
    ReplayOnChangePolicy,
    TransformStep,
)
from streambuild.compiler.discovery.types import (
    ReplayAnchorMode,
    ReplayBoundaryMode,
    ReplayLineageMode,
    SourceKind,
)
from streambuild.compiler.pipeline.main._realize_project import realize_project
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis, RealizedProject
from streambuild.compiler.planner.main.plan_standard_build import plan_standard_build
from streambuild.compiler.planner.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualStateInspection,
    ActualTable,
    DeploymentRecord,
    DeploymentRuntimeDetailRecord,
    DeploymentWatermarkRecord,
    ObjectStateRecord,
    PreparedObjectMapping,
    PublishEventRecord,
    RootDeploymentInspection,
    StandardPlan,
    StandardRelationOperation,
    StandardWarehouseSnapshot,
)
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer
from tests.unit.src.streambuild.compiler.compile.helpers import build_realization_analyzer

EXAMPLE_PIPELINE_FILE_PATH: Path = Path(
    "tests/fixtures/basic_project/pipelines/orders/pipeline.yml"
)


def compile_pipeline(loaded_pipeline: LoadedPipeline) -> CompiledPipeline:
    return compile_pipeline_impl(
        loaded_pipeline=loaded_pipeline,
        sql_analyzer=SqlModelAnalyzer(dialect="clickhouse"),
    )


class SnapshotRecordingConnection(AdapterConnection):
    def __init__(
        self,
        *,
        catalog: CatalogSnapshot,
        metadata_result: AdapterQueryResult,
        virtual_environments: bool,
        standard_rebuild: bool = True,
        ownership_records: tuple[AdapterOwnershipRecord, ...] = (),
    ) -> None:
        self._catalog: CatalogSnapshot = catalog
        self._metadata_result: AdapterQueryResult = metadata_result
        self._ownership_records: tuple[AdapterOwnershipRecord, ...] = ownership_records
        self.recorded_ownership_records: tuple[AdapterOwnershipRecord, ...] = ()
        self.ownership_databases: list[str] = []
        self._capabilities: AdapterCapabilities = AdapterCapabilities(
            virtual_environments=virtual_environments,
            managed_source_kinds=frozenset({"kafka"}),
            replay_boundary_modes=frozenset(AdapterReplayBoundaryMode),
            history_prefix_seed=True,
            stable_logical_bindings=True,
            per_relation_atomic_replace=True,
            graph_atomic_publish=False,
            set_difference_comparison=True,
            standard_rebuild=standard_rebuild,
        )
        self.catalog_load_count: int = 0
        self.query_count: int = 0

    @property
    def adapter_identity(self) -> AdapterIdentity:
        return self._catalog.identity.adapter

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    def load_catalog(self, database: str) -> CatalogSnapshot:
        del database
        self.catalog_load_count += 1
        return self._catalog

    def metadata_columns(self, *, database: str, table: str) -> frozenset[str]:
        del database, table
        return frozenset()

    def load_target_ownership(self, database: str) -> tuple[AdapterOwnershipRecord, ...]:
        self.ownership_databases.append(database)
        return self._ownership_records

    def record_target_ownership(
        self, *, database: str, records: tuple[AdapterOwnershipRecord, ...]
    ) -> None:
        del database
        self.recorded_ownership_records = (*self.recorded_ownership_records, *records)

    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        del database
        return InspectedManagedTableState(active_bindings=(), physical_candidates=())

    def command(self, statement: str) -> None:
        del statement

    def query(self, statement: str) -> AdapterQueryResult:
        del statement
        self.query_count += 1
        return self._metadata_result

    def insert_rows(self, *, table: str, rows: tuple[dict[str, object], ...]) -> None:
        del table, rows

    def ensure_database(self, database: str) -> None:
        del database

    def render_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> str:
        return ClickHouseAdapter().render_resource(
            resource=resource,
            database=database,
            if_not_exists=if_not_exists,
        )

    def realize_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        del resource, database, if_not_exists

    def migrate_metadata_state(self, database: str) -> None:
        del database

    def persist_metadata_state(self, *, database: str, state: AdapterMetadataState) -> None:
        del database, state

    def load_deployment_inventory(self, database: str) -> AdapterDeploymentInventory:
        del database
        return AdapterDeploymentInventory(deployments=(), publish_events=())

    def execute_replay(self, request: AdapterReplayRequest) -> None:
        del request

    def compare_readiness(
        self, request: AdapterReadinessRequest
    ) -> tuple[AdapterReadinessRootObservation, ...]:
        del request
        return ()

    def replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> AdapterBindingReplacementResult:
        return AdapterBindingReplacementResult(
            bindings=request.bindings,
            per_relation_atomic_replace=True,
            graph_atomic_publish=False,
        )

    def cleanup_relations(
        self, request: AdapterRelationCleanupRequest
    ) -> AdapterRelationCleanupResult:
        return AdapterRelationCleanupResult(relation_names=request.relation_names)

    def close(self) -> None:
        return None


def build_snapshot_catalog() -> CatalogSnapshot:
    return CatalogSnapshot(
        identity=CatalogIdentity(
            adapter=AdapterIdentity(name="clickhouse"),
            database="analytics",
        ),
        warehouse_timezone="UTC",
        relations=(
            CatalogRelation(
                name="tbl__orders",
                engine="MergeTree",
                columns=(CatalogColumn(name="order_id", type="String"),),
            ),
        ),
    )


def realize_compiled_pipelines(
    compiled_pipelines: tuple[CompiledPipeline, ...],
) -> RealizedProject:
    sources_by_name: dict[str, CompiledSource] = {
        pipeline.source.key.name: pipeline.source for pipeline in compiled_pipelines
    }
    compiled_project: CompiledProject = CompiledProject(
        sources=tuple(sources_by_name.values()),
        models=tuple(chain.from_iterable(pipeline.models for pipeline in compiled_pipelines)),
        pipelines=compiled_pipelines,
        tests=(),
        test_cases=(),
        audits=(),
    )
    sql_analyzer: SqlModelAnalyzer = build_realization_analyzer(compiled_project)
    adapter_profile: CompilerAdapterProfile = build_compiler_adapter_profile(ClickHouseAdapter())
    return realize_project(
        project=compiled_project,
        adapter_profile=adapter_profile,
        sql_analyzer=sql_analyzer,
    )


def build_metadata_records() -> tuple[
    tuple[ObjectStateRecord, ...],
    tuple[DeploymentRecord, ...],
    tuple[DeploymentWatermarkRecord, ...],
    tuple[DeploymentRuntimeDetailRecord, ...],
    tuple[PublishEventRecord, ...],
]:
    root_key: ObjectKey = ObjectKey(
        database=None, object_type=DESIRED_OBJECT_TYPE_TABLE, name="raw__orders"
    )
    transform_key: ObjectKey = ObjectKey(
        database=None,
        object_type=DESIRED_OBJECT_TYPE_TABLE,
        name="tbl__orders_enriched",
    )
    mv_key: ObjectKey = ObjectKey(
        database=None,
        object_type=DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
        name="mv__orders_enriched",
    )
    object_states: tuple[ObjectStateRecord, ...] = (
        ObjectStateRecord(
            deployment_id="20260408T120000Z_ab12cd",
            key=transform_key,
            normalized_fingerprint="fingerprint_transform",
            normalized_query="SELECT * FROM raw__orders",
            recorded_at="2026-04-08T12:00:00Z",
        ),
        ObjectStateRecord(
            deployment_id="20260408T120000Z_ab12cd",
            key=mv_key,
            normalized_fingerprint="fingerprint_mv",
            normalized_query="SELECT * FROM raw__orders",
            recorded_at="2026-04-08T12:00:01Z",
        ),
    )
    deployments: tuple[DeploymentRecord, ...] = (
        DeploymentRecord(
            deployment_id="20260408T130000Z_cd34ef",
            created_at="2026-04-08T13:00:00Z",
            status="backfilling",
            replay_lineage_mode="offsets",
            selected_root_keys=(transform_key, root_key),
            warning_codes=("z_warning", "a_warning"),
            prepared_object_mappings=(
                PreparedObjectMapping(
                    logical_key=mv_key,
                    physical_name="mv__orders_enriched__20260408T130000Z_cd34ef",
                ),
                PreparedObjectMapping(
                    logical_key=transform_key,
                    physical_name="tbl__orders_enriched__20260408T130000Z_cd34ef",
                ),
            ),
        ),
        DeploymentRecord(
            deployment_id="20260408T120000Z_ab12cd",
            created_at="2026-04-08T12:00:00Z",
            status="published",
            replay_lineage_mode="timestamp",
            selected_root_keys=(root_key,),
            warning_codes=(),
            prepared_object_mappings=(),
        ),
    )
    watermarks: tuple[DeploymentWatermarkRecord, ...] = (
        DeploymentWatermarkRecord(
            deployment_id="20260408T130000Z_cd34ef",
            root_key=transform_key,
            anchor_key=root_key,
            boundary_key="partition:1",
            cutoff_value="54321",
        ),
        DeploymentWatermarkRecord(
            deployment_id="20260408T130000Z_cd34ef",
            root_key=transform_key,
            anchor_key=root_key,
            boundary_key="partition:0",
            cutoff_value="12345",
        ),
    )
    runtime_details: tuple[DeploymentRuntimeDetailRecord, ...] = (
        DeploymentRuntimeDetailRecord(
            deployment_id="20260408T130000Z_cd34ef",
            root_key=transform_key,
            state_kind="active_view_present",
            replay_strategy="bounded_replay",
            active_deployment_id="20260408T120000Z_ab12cd",
            anchor_key=root_key,
            anchor_physical_name="raw__orders__20260408T130000Z_ab12cd",
            execution_mode="seeded_bounded_rebuild",
            configured_backfill_mode="bounded",
            execution_lookback_seconds=604800,
            live_target_names=("tbl__orders_enriched",),
        ),
    )
    publish_events: tuple[PublishEventRecord, ...] = (
        PublishEventRecord(
            deployment_id="20260408T120000Z_ab12cd",
            published_at="2026-04-08T12:30:00Z",
            logical_view_names=("tbl__orders_enriched",),
        ),
    )
    return object_states, deployments, watermarks, runtime_details, publish_events


def build_example_desired_state() -> DesiredState:
    loaded_pipeline: LoadedPipeline = load_pipeline_file(EXAMPLE_PIPELINE_FILE_PATH)
    return realize_compiled_pipelines((compile_pipeline(loaded_pipeline),)).desired_state


def build_single_transform_desired_state(
    *,
    query: str,
    replay_lineage_mode: ReplayLineageMode | str = ReplayLineageMode.OFFSETS,
    replay_anchor: ReplayAnchorMode | str = ReplayAnchorMode.AUTO,
    order_by: tuple[str, ...] = ("order_id",),
    supporting_transforms: tuple[tuple[str, str, tuple[str, ...]], ...] = (),
) -> DesiredState:
    resolved_replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(replay_lineage_mode)
    resolved_replay_anchor: ReplayAnchorMode = ReplayAnchorMode(replay_anchor)
    supporting_transform_steps: list[TransformStep] = [
        TransformStep(
            name=name,
            source="orders",
            engine="MergeTree()",
            order_by=list(transform_order_by),
            query=transform_query,
        )
        for name, transform_query, transform_order_by in supporting_transforms
    ]
    pipeline: Pipeline = Pipeline(
        name="tmp_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders",
                consumer_group="streambuild_tmp_pipeline_orders",
            ),
            replay_boundary=ReplayBoundary(
                mode=ReplayBoundaryMode(resolved_replay_lineage_mode),
                columns=ReplayBoundaryColumns(),
            ),
        ),
        transforms=[
            *supporting_transform_steps,
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=list(order_by),
                query=query,
                replay_anchor=resolved_replay_anchor,
            ),
        ],
    )
    loaded_pipeline: LoadedPipeline = LoadedPipeline(
        pipeline=pipeline,
        file_path=EXAMPLE_PIPELINE_FILE_PATH,
    )
    return realize_compiled_pipelines((compile_pipeline(loaded_pipeline),)).desired_state


def build_preservation_matrix_compiled_pipeline(
    *, source_ownership: str, replay_lineage_mode: ReplayLineageMode | str
) -> CompiledPipeline:
    resolved_replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(replay_lineage_mode)
    builder: Callable[[ReplayLineageMode], CompiledPipeline] = PRESERVATION_PIPELINE_BUILDERS[
        source_ownership
    ]
    return builder(resolved_replay_lineage_mode)


def _build_managed_preservation_compiled_pipeline(
    replay_lineage_mode: ReplayLineageMode,
) -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="preservation_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders",
            ),
            replay_boundary=ReplayBoundary(
                mode=ReplayBoundaryMode(replay_lineage_mode),
                columns=ReplayBoundaryColumns(),
            ),
        ),
        transforms=[_build_preservation_transform(replay_lineage_mode)],
    )
    return compile_pipeline(LoadedPipeline(pipeline=pipeline, file_path=EXAMPLE_PIPELINE_FILE_PATH))


def _build_adopted_preservation_compiled_pipeline(
    replay_lineage_mode: ReplayLineageMode,
) -> CompiledPipeline:
    replay_boundary_mode: ReplayBoundaryMode = ReplayBoundaryMode(replay_lineage_mode)
    pipeline: Pipeline = Pipeline(
        name="preservation_pipeline",
        source=ExternalTableSourceStep(
            name="orders",
            kind=PRESERVATION_EXTERNAL_SOURCE_KIND_BY_MODE[replay_lineage_mode],
            table_name="orders_existing",
            replay_boundary=ReplayBoundary(
                mode=replay_boundary_mode,
                columns=PRESERVATION_BOUNDARY_COLUMNS_BY_MODE[replay_lineage_mode],
            ),
        ),
        transforms=[_build_preservation_transform(replay_lineage_mode)],
    )
    return compile_pipeline(LoadedPipeline(pipeline=pipeline, file_path=EXAMPLE_PIPELINE_FILE_PATH))


def _build_preservation_transform(replay_lineage_mode: ReplayLineageMode) -> TransformStep:
    return TransformStep(
        name="orders_enriched",
        source="orders",
        engine="MergeTree()",
        order_by=["order_id"],
        query=(
            "SELECT CAST(order_id AS String) AS order_id, "
            + PRESERVATION_PROJECTION_BY_MODE[replay_lineage_mode]
            + ' FROM __ref("orders")'
        ),
        replay_anchor=ReplayAnchorMode.NEVER,
    )


PRESERVATION_PIPELINE_BUILDERS: dict[str, Callable[[ReplayLineageMode], CompiledPipeline]] = {
    "managed": _build_managed_preservation_compiled_pipeline,
    "adopted": _build_adopted_preservation_compiled_pipeline,
}
PRESERVATION_EXTERNAL_SOURCE_KIND_BY_MODE: dict[ReplayLineageMode, SourceKind] = {
    ReplayLineageMode.OFFSETS: SourceKind.KAFKA,
    ReplayLineageMode.TIMESTAMP: SourceKind.KAFKA,
    ReplayLineageMode.CURSOR: SourceKind.STREAM_TABLE,
}
PRESERVATION_BOUNDARY_COLUMNS_BY_MODE: dict[ReplayLineageMode, ReplayBoundaryColumns] = {
    ReplayLineageMode.OFFSETS: ReplayBoundaryColumns(
        partition="event_partition",
        offset="event_offset",
        timestamp="event_timestamp",
    ),
    ReplayLineageMode.TIMESTAMP: ReplayBoundaryColumns(timestamp="event_timestamp"),
    ReplayLineageMode.CURSOR: ReplayBoundaryColumns(
        timestamp="event_timestamp",
        cursor="event_cursor",
    ),
}
PRESERVATION_PROJECTION_BY_MODE: dict[ReplayLineageMode, str] = {
    ReplayLineageMode.OFFSETS: (
        "CAST(_replay_partition AS Int32) AS _replay_partition, "
        "CAST(_replay_offset AS Int64) AS _replay_offset"
    ),
    ReplayLineageMode.TIMESTAMP: ("CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp"),
    ReplayLineageMode.LANDED_AT: ("CAST(_replay_landed_at AS DateTime64(3)) AS _replay_landed_at"),
    ReplayLineageMode.CURSOR: "CAST(_replay_cursor AS UInt64) AS _replay_cursor",
}


def build_mutable_ref_desired_state() -> DesiredState:
    return build_single_transform_desired_state(
        query=(
            "SELECT CAST(order_id AS UInt64) AS order_id, "
            "CAST(_replay_partition AS UInt64) AS _replay_partition, "
            "CAST(_replay_offset AS UInt64) AS _replay_offset "
            'FROM __ref("orders") LEFT JOIN '
            '__ref("customers", ref_type="mutable") USING customer_id'
        ),
        supporting_transforms=(
            (
                "customers",
                'SELECT CAST(customer_id AS UInt64) AS customer_id FROM __ref("orders")',
                ("customer_id",),
            ),
        ),
    )


STANDARD_SCOPE_MODEL_SQL_BY_NAME: dict[str, str] = {
    "alpha": 'SELECT order_id::UInt64 AS order_id FROM __source("orders")',
    "beta": 'SELECT order_id::UInt64 AS order_id FROM __ref("alpha")',
    "gamma": 'SELECT order_id::UInt64 AS order_id FROM __ref("beta")',
    "delta": (
        'SELECT a.order_id::UInt64 AS order_id FROM __ref("alpha") AS a '
        'LEFT JOIN __ref("gamma", ref_type="reference") AS g ON a.order_id = g.order_id'
    ),
}
STANDARD_SCOPE_MODEL_NAMES: tuple[str, ...] = ("alpha", "beta", "gamma", "delta")
STANDARD_SCOPE_SOURCE_RELATION_NAMES: tuple[str, ...] = (
    "kafka__orders",
    "raw__orders",
    "mv__orders",
)
_STANDARD_SCOPE_SETTINGS_BLOCK_BY_FLAG: dict[bool | None, str] = {
    None: "",
    True: "\n[settings]\nvirtual_environments = true\n",
    False: "\n[settings]\nvirtual_environments = false\n",
}
_STANDARD_SCOPE_SOURCE_YML: str = (
    "sources:\n"
    "  - name: orders\n"
    "    kind: kafka\n"
    "    broker_list: kafka:9092\n"
    "    topic: source.orders\n"
    "    replay_boundary: {mode: offsets}\n"
)


def write_standard_scope_project(
    *, project_root: Path, virtual_environments: bool | None = None
) -> None:
    """Write the alpha/beta/gamma/delta scope project used by standard planning tests."""

    pipeline_root: Path = project_root / "pipelines" / "orders"
    source_root: Path = project_root / "sources"
    pipeline_root.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    (project_root / "streambuild_project.toml").write_text(
        'name = "standard_scope"\n'
        'default_target = "test"\n'
        f"{_STANDARD_SCOPE_SETTINGS_BLOCK_BY_FLAG[virtual_environments]}"
        "\n[targets.test]\n"
        'database = "analytics"\n',
        encoding="utf-8",
    )
    (source_root / "orders.yml").write_text(_STANDARD_SCOPE_SOURCE_YML, encoding="utf-8")
    (pipeline_root / "pipeline.yml").write_text("source: orders\n", encoding="utf-8")
    model_name: str
    model_sql: str
    for model_name, model_sql in STANDARD_SCOPE_MODEL_SQL_BY_NAME.items():
        (pipeline_root / f"{model_name}.sql").write_text(
            f'MODEL (order_by: ["order_id"]);\n{model_sql}\n',
            encoding="utf-8",
        )


def write_standard_mutable_scope_project(*, project_root: Path) -> None:
    """Write the standard scope with delta using a mutable side reference."""

    write_standard_scope_project(project_root=project_root)
    delta_path: Path = project_root / "pipelines" / "orders" / "delta.sql"
    delta_path.write_text(
        delta_path.read_text(encoding="utf-8").replace(
            'ref_type="reference"', 'ref_type="mutable"'
        ),
        encoding="utf-8",
    )


def analyze_standard_scope_project(*, project_root: Path) -> CompileAnalysis:
    """Analyze a written scope project exactly as the CLI does."""

    return analyze_project(
        pipelines_root=project_root / "pipelines",
        loaded_project=load_project_input_for_path(path=project_root),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )


def standard_model_keys(
    *, analysis: CompileAnalysis, names: tuple[str, ...]
) -> frozenset[LogicalResourceKey]:
    """Return the logical model keys for the named models."""

    key_by_name: dict[str, LogicalResourceKey] = {
        key.name: key for key in analysis.graph.ordered_keys
    }
    return frozenset(key_by_name[name] for name in names)


def build_standard_snapshot(
    *,
    relation_names: tuple[str, ...] = (),
    standard_owned_names: tuple[str, ...] = (),
    virtual_environment_owned_names: tuple[str, ...] = (),
    stable_binding_names: tuple[str, ...] = (),
    ownership_database: str = "analytics",
) -> StandardWarehouseSnapshot:
    """Build one immutable standard snapshot from explicit relation and ownership facts."""

    stable_binding_by_name: dict[str, str | None] = {
        relation_name: f"{relation_name}__binding" for relation_name in stable_binding_names
    }
    return StandardWarehouseSnapshot(
        catalog=CatalogSnapshot(
            identity=CatalogIdentity(
                adapter=AdapterIdentity(name="clickhouse"),
                database="analytics",
            ),
            warehouse_timezone="UTC",
            relations=tuple(
                CatalogRelation(
                    name=relation_name,
                    engine="MergeTree",
                    columns=(CatalogColumn(name="order_id", type="UInt64"),),
                    stable_binding_name=stable_binding_by_name.get(relation_name),
                )
                for relation_name in relation_names
            ),
        ),
        ownership_records=(
            *_ownership_records(
                relation_names=standard_owned_names,
                mode=AdapterOwningMode.STANDARD,
                database=ownership_database,
            ),
            *_ownership_records(
                relation_names=virtual_environment_owned_names,
                mode=AdapterOwningMode.VIRTUAL_ENVIRONMENT,
                database=ownership_database,
            ),
        ),
    )


def _ownership_records(
    *, relation_names: tuple[str, ...], mode: AdapterOwningMode, database: str
) -> tuple[AdapterOwnershipRecord, ...]:
    return tuple(
        AdapterOwnershipRecord(
            database_name=database,
            relation_name=relation_name,
            resource_kind="table",
            logical_model_name=relation_name.split("__")[-1],
            owning_mode=mode,
            tool_version="test",
        )
        for relation_name in relation_names
    )


def plan_standard_scope(
    *,
    analysis: CompileAnalysis,
    snapshot: StandardWarehouseSnapshot,
    selected_model_names: tuple[str, ...],
) -> StandardPlan:
    """Plan the standard closure of the scope project for the named selection."""

    return plan_standard_build(
        graph=analysis.graph,
        realized_project=analysis.realized_project,
        snapshot=snapshot,
        database="analytics",
        selected_model_keys=standard_model_keys(analysis=analysis, names=selected_model_names),
    )


def logical_key_names(keys: tuple[LogicalResourceKey, ...]) -> tuple[str, ...]:
    """Return the names of logical resource keys in their original order."""

    return tuple(key.name for key in keys)


def replay_root_summaries(*, plan: StandardPlan) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """Summarize each replay root as model, driving relation, and propagated models."""

    return tuple(
        (
            root.model_key.name,
            root.driving_input_relation_name,
            logical_key_names(root.propagated_model_keys),
        )
        for root in plan.replay_roots
    )


def relation_operation_summaries(
    *, operations: tuple[StandardRelationOperation, ...]
) -> tuple[tuple[str, str], ...]:
    """Summarize relation operations as ordered action and relation-name pairs."""

    return tuple((str(operation.action), operation.relation_name) for operation in operations)


def build_settled_standard_snapshot() -> StandardWarehouseSnapshot:
    """Build the snapshot of a warehouse that standard mode already built end to end."""

    model_relation_names: tuple[str, ...] = standard_scope_relation_names(
        model_names=STANDARD_SCOPE_MODEL_NAMES
    )
    return build_standard_snapshot(
        relation_names=(*STANDARD_SCOPE_SOURCE_RELATION_NAMES, *model_relation_names),
        standard_owned_names=model_relation_names,
    )


def standard_scope_relation_names(*, model_names: tuple[str, ...]) -> tuple[str, ...]:
    """Return the table and view relation names owned by the named models."""

    return tuple(
        chain.from_iterable(
            (f"tbl__{model_name}", f"mv__{model_name}") for model_name in model_names
        )
    )


def build_key(database: str | None, object_type: str, name: str) -> ObjectKey:
    return ObjectKey(database=database, object_type=DesiredObjectType(object_type), name=name)


def build_example_desired_state_with_replay_on_change(
    *, replay_on_change: ReplayOnChangePolicy | None
) -> DesiredState:
    """Build the example desired state with replay-on-change on every transform."""

    loaded_pipeline: LoadedPipeline = load_pipeline_file(EXAMPLE_PIPELINE_FILE_PATH)
    pipeline_with_policy: Pipeline = replace(
        loaded_pipeline.pipeline,
        transforms=[
            replace(transform_step, replay_on_change=replay_on_change)
            for transform_step in loaded_pipeline.pipeline.transforms
        ],
    )
    return realize_compiled_pipelines(
        (compile_pipeline(replace(loaded_pipeline, pipeline=pipeline_with_policy)),)
    ).desired_state


def build_example_actual_state() -> ActualState:
    desired_state: DesiredState = build_example_desired_state()
    kafka_table: DesiredKafkaTable | DesiredTable | DesiredMaterializedView = desired_state.objects[
        0
    ]
    landing_mv: DesiredKafkaTable | DesiredTable | DesiredMaterializedView = desired_state.objects[
        1
    ]
    raw_table: DesiredKafkaTable | DesiredTable | DesiredMaterializedView = desired_state.objects[3]
    assert isinstance(kafka_table, DesiredKafkaTable)
    assert isinstance(landing_mv, DesiredMaterializedView)
    assert isinstance(raw_table, DesiredTable)

    return ActualState(
        objects=(
            ActualKafkaTable(
                key=kafka_table.key,
                spec=KafkaTableSpec(
                    columns=kafka_table.spec.columns,
                    kafka=kafka_table.spec.kafka,
                ),
            ),
            ActualMaterializedView(
                key=landing_mv.key,
                spec=MaterializedViewSpec(
                    source_table_name=landing_mv.spec.source_table_name,
                    target_table_name=landing_mv.spec.target_table_name,
                    query=landing_mv.spec.query,
                ),
            ),
            ActualTable(
                key=raw_table.key,
                spec=TableSpec(
                    columns=raw_table.spec.columns,
                    storage=TableStorage(
                        engine=raw_table.spec.storage.engine,
                        order_by=raw_table.spec.storage.order_by,
                        partition_by=raw_table.spec.storage.partition_by,
                        ttl=raw_table.spec.storage.ttl,
                        settings={"index_granularity": "4096"},
                    ),
                ),
            ),
        )
    )


def build_actual_state_matching_desired(desired_state: DesiredState) -> ActualState:
    actual_object_builders: dict[type[object], Callable[..., object]] = {
        DesiredKafkaTable: ActualKafkaTable,
        DesiredMaterializedView: ActualMaterializedView,
        DesiredTable: ActualTable,
    }
    actual_objects: tuple[ActualKafkaTable | ActualMaterializedView | ActualTable, ...] = tuple(
        cast(
            ActualKafkaTable | ActualMaterializedView | ActualTable,
            actual_object_builders[type(desired_object)](
                key=desired_object.key,
                spec=desired_object.spec,
            ),
        )
        for desired_object in desired_state.objects
    )
    return ActualState(objects=actual_objects)


def build_actual_objects() -> tuple[ActualKafkaTable | ActualTable | ActualMaterializedView, ...]:
    kafka_spec: KafkaTableSpec = KafkaTableSpec(
        columns=(Column(name="message", type="String"),),
        kafka=CompiledKafkaSettings(
            broker_list="kafka:9092",
            topic="source.orders.created",
            consumer_group="streambuild_orders_orders",
            format="JSONAsString",
            settings={"kafka_num_consumers": "4"},
        ),
    )
    table_spec: TableSpec = TableSpec(
        columns=(
            Column(name="order_id", type="String"),
            Column(name="updated_at", type="DateTime64(3)"),
        ),
        storage=TableStorage(
            engine="ReplacingMergeTree(updated_at)",
            order_by=("order_id", "updated_at"),
            partition_by="toYYYYMM(updated_at)",
            ttl="toDateTime(updated_at) + INTERVAL 30 DAY",
            settings={"index_granularity": "8192"},
        ),
    )
    materialized_view_spec: MaterializedViewSpec = MaterializedViewSpec(
        source_table_name="raw__orders",
        target_table_name="tbl__orders_enriched",
        query="SELECT * FROM raw__orders",
    )
    return (
        ActualTable(
            key=ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_TABLE,
                name="tbl__orders_enriched",
            ),
            spec=table_spec,
        ),
        ActualMaterializedView(
            key=ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
                name="mv__orders_enriched",
            ),
            spec=materialized_view_spec,
        ),
        ActualKafkaTable(
            key=ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_KAFKA_TABLE,
                name="kafka__orders",
            ),
            spec=kafka_spec,
        ),
    )


def build_projection_characterization_inputs() -> tuple[DesiredState, ActualStateInspection]:
    kafka_key: ObjectKey = ObjectKey(database=None, object_type="kafka_table", name="kafka__orders")
    raw_key: ObjectKey = ObjectKey(database=None, object_type="table", name="raw__orders")
    landing_mv_key: ObjectKey = ObjectKey(
        database=None,
        object_type="materialized_view",
        name="mv__orders_landing",
    )
    transform_key: ObjectKey = ObjectKey(
        database=None, object_type="table", name="tbl__orders_enriched"
    )
    raw_storage: TableStorage = TableStorage(
        engine="MergeTree()",
        order_by=("order_id",),
        partition_by="toYYYYMM(created_at)",
        ttl="created_at + INTERVAL 30 DAY",
        settings={"index_granularity": "8192"},
    )
    desired_state: DesiredState = DesiredState(
        objects=(
            DesiredKafkaTable(
                key=kafka_key,
                deps=(),
                spec=KafkaTableSpec(
                    columns=(Column(name="message", type="String"),),
                    kafka=CompiledKafkaSettings(
                        broker_list="kafka:9092",
                        topic="source.orders.created",
                        consumer_group="streambuild_orders_orders",
                        format="JSONAsString",
                        settings={"kafka_num_consumers": "4"},
                    ),
                ),
            ),
            DesiredTable(
                key=raw_key,
                deps=(kafka_key,),
                spec=TableSpec(
                    columns=(Column(name="order_id", type="String"),),
                    storage=raw_storage,
                ),
            ),
            DesiredMaterializedView(
                key=landing_mv_key,
                deps=(kafka_key, raw_key),
                spec=MaterializedViewSpec(
                    source_table_name="kafka__orders",
                    target_table_name="raw__orders",
                    query="SELECT message AS order_id FROM kafka__orders",
                ),
            ),
            DesiredTable(
                key=transform_key,
                deps=(raw_key,),
                spec=TableSpec(
                    columns=(Column(name="order_id", type="String"),),
                    storage=raw_storage,
                ),
            ),
        ),
        replay_anchor_keys=frozenset({raw_key}),
        mutable_ref_warning_keys=frozenset(),
    )
    inspection: ActualStateInspection = ActualStateInspection(
        existing_names=frozenset({kafka_key.name, raw_key.name, landing_mv_key.name}),
        active_deployment_by_root={
            transform_key: RootDeploymentInspection(
                root_key=transform_key,
                state_kind="active_view_present",
                active_deployment_id="dep_a",
            )
        },
        object_state_by_deployment_and_key={},
        latest_object_state_by_key={},
        active_physical_names_by_logical_name={transform_key.name: "tbl__orders_enriched__dep_a"},
        active_table_specs_by_name={
            "tbl__orders_enriched__dep_a": TableSpec(
                columns=(Column(name="order_id", type="String"),),
                storage=TableStorage(
                    engine="MergeTree()",
                    order_by=("order_id",),
                    ttl=None,
                    settings=None,
                ),
            )
        },
    )
    return desired_state, inspection


KeyParts: type = tuple[str | None, str, str]


def key_parts(key: ObjectKey) -> KeyParts:
    """Return a key as a comparable tuple."""

    return (key.database, key.object_type, key.name)


def optional_key_parts(key: ObjectKey | None) -> KeyParts | None:
    """Return a key as a comparable tuple, preserving an absent key as None."""

    resolvers: dict[type[object], Callable[[], tuple[str | None, str, str] | None]] = {
        type(None): lambda: None,
        ObjectKey: lambda: key_parts(cast(ObjectKey, key)),
    }
    return resolvers[type(key)]()
