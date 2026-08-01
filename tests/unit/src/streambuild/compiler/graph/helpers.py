from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledSource,
    CompiledTableModel,
    CompiledViewModel,
    LogicalResourceKey,
    ParsedRef,
)
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.discovery.models import (
    KafkaLandingStep,
    KafkaSettings,
    TransformStep,
    ViewStep,
)
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    ModelKind,
    RefType,
    ReplayLineageMode,
    SqlRelationType,
)
from streambuild.compiler.sql_analysis.models import (
    SqlAggregateFacts,
    SqlModelAnalysis,
    SqlReference,
    SqlSourceSpan,
)
from streambuild.compiler.sql_analysis.types import RefType as AnalysisRefType
from streambuild.compiler.sql_analysis.types import SqlQueryShape

_ANALYSIS_REF_TYPE_BY_DISCOVERY: dict[RefType | None, AnalysisRefType | None] = {
    None: None,
    RefType.REFERENCE: AnalysisRefType.REFERENCE,
    RefType.MUTABLE: AnalysisRefType.MUTABLE,
}


def build_typed_graph_project() -> CompiledProject:
    return CompiledProject(
        sources=(_compiled_source("orders"),),
        models=(
            _compiled_model(
                name="enriched",
                source_name="cleaned",
                parsed_refs=(
                    _driving_ref("cleaned"),
                    _side_ref(name="lookup", ref_type=RefType.REFERENCE),
                    _side_ref(name="mutable_rates", ref_type=RefType.MUTABLE),
                ),
            ),
            _compiled_model(
                name="mutable_rates",
                source_name="orders",
                parsed_refs=(_driving_ref("orders"),),
            ),
            _compiled_model(
                name="lookup",
                source_name="orders",
                parsed_refs=(_driving_ref("orders"),),
            ),
            _compiled_model(
                name="cleaned",
                source_name="orders",
                parsed_refs=(_driving_ref("orders"),),
            ),
        ),
        pipelines=(),
        tests=(),
        test_cases=(),
        audits=(),
    )


def build_cyclic_graph_project() -> CompiledProject:
    return CompiledProject(
        sources=(_compiled_source("orders"),),
        models=(
            _compiled_model(
                name="alpha",
                source_name="beta",
                parsed_refs=(_driving_ref("beta"),),
            ),
            _compiled_model(
                name="beta",
                source_name="alpha",
                parsed_refs=(_driving_ref("alpha"),),
            ),
        ),
        pipelines=(),
        tests=(),
        test_cases=(),
        audits=(),
    )


def build_terminal_view_graph_project() -> CompiledProject:
    return CompiledProject(
        sources=(_compiled_source("orders"),),
        models=(
            _compiled_model(
                name="lookup",
                source_name="orders",
                parsed_refs=(_driving_ref("orders"),),
            ),
            _compiled_view(
                name="summary",
                parsed_refs=(_source_ref("orders"), _driving_ref("lookup")),
            ),
        ),
        pipelines=(),
        tests=(),
        test_cases=(),
        audits=(),
    )


def build_nonterminal_view_graph_project() -> CompiledProject:
    terminal_project: CompiledProject = build_terminal_view_graph_project()
    return CompiledProject(
        sources=terminal_project.sources,
        models=(
            *terminal_project.models,
            _compiled_model(
                name="consumer",
                source_name="orders",
                parsed_refs=(
                    _driving_ref("orders"),
                    _side_ref(name="summary", ref_type=RefType.REFERENCE),
                ),
            ),
        ),
        pipelines=(),
        tests=(),
        test_cases=(),
        audits=(),
    )


def logical_key(name: str) -> LogicalResourceKey:
    return LogicalResourceKey(resource_type=LogicalResourceType.MODEL, name=name)


def _compiled_source(name: str) -> CompiledSource:
    return CompiledSource(
        key=LogicalResourceKey(resource_type=LogicalResourceType.SOURCE, name=name),
        source=KafkaLandingStep(
            name=name,
            kafka=KafkaSettings(broker_list="kafka:9092", topic=f"source.{name}"),
        ),
        effective_replay_lineage_mode=ReplayLineageMode.OFFSETS,
    )


def _compiled_model(
    *, name: str, source_name: str, parsed_refs: tuple[ParsedRef, ...]
) -> CompiledModel:
    return CompiledTableModel(
        key=logical_key(name),
        pipeline_name="graph",
        relation_name=f"tbl__{name}",
        kind=ModelKind.TABLE,
        transform=TransformStep(
            name=name,
            source=source_name,
            engine="MergeTree()",
            order_by=("id",),
            query="SELECT 1 AS id",
        ),
        sql_analysis=_sql_analysis(parsed_refs),
        preserves_required_lineage=True,
        replay_anchor_eligible=True,
        effective_bounded_replay_fallback=BoundedReplayFallback.FULL,
    )


def _compiled_view(*, name: str, parsed_refs: tuple[ParsedRef, ...]) -> CompiledViewModel:
    return CompiledViewModel(
        key=logical_key(name),
        pipeline_name="graph",
        relation_name=f"view__{name}",
        kind=ModelKind.VIEW,
        sql_analysis=_sql_analysis(parsed_refs),
        view=ViewStep(name=name, query="SELECT 1 AS id"),
    )


def _sql_analysis(parsed_refs: tuple[ParsedRef, ...]) -> SqlModelAnalysis:
    span: SqlSourceSpan = SqlSourceSpan(
        start=0,
        end=1,
        line=1,
        column=1,
        end_line=1,
        end_column=2,
    )
    return SqlModelAnalysis(
        authored_sql="SELECT 1 AS id",
        canonical_sql="SELECT 1 AS id",
        shape=SqlQueryShape.SELECT,
        projections=(),
        references=tuple(
            SqlReference(
                name=parsed_ref.name,
                relation_type=parsed_ref.relation_type,
                ref_type=_ANALYSIS_REF_TYPE_BY_DISCOVERY[parsed_ref.ref_type],
                span=span,
            )
            for parsed_ref in parsed_refs
        ),
        storage_expressions=(),
        aggregate_facts=SqlAggregateFacts(
            has_group_by=False,
            function_names=(),
            engine_name="MergeTree",
            engine_has_aggregate_semantics=False,
        ),
    )


def _driving_ref(name: str) -> ParsedRef:
    return ParsedRef(name=name, relation_type=SqlRelationType.REF, ref_type=None)


def _source_ref(name: str) -> ParsedRef:
    return ParsedRef(name=name, relation_type=SqlRelationType.SOURCE, ref_type=None)


def _side_ref(*, name: str, ref_type: RefType) -> ParsedRef:
    return ParsedRef(name=name, relation_type=SqlRelationType.REF, ref_type=ref_type)
