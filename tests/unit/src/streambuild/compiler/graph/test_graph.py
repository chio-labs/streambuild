from pathlib import Path
from types import MappingProxyType

import pytest

from streambuild.compiler.compile.models import CompiledProject
from streambuild.compiler.graph.constants import (
    ALL_DEPENDENCY_EDGE_TYPES,
    DRIVING_DEPENDENCY_EDGE_TYPES,
)
from streambuild.compiler.graph.exceptions import GraphInputError
from streambuild.compiler.graph.main._build_project_graph import (
    build_project_graph_from_compiled_project,
)
from streambuild.compiler.graph.main.collect_reachable_keys import collect_reachable_keys
from streambuild.compiler.graph.models import DependencyEdge, ProjectGraph
from streambuild.compiler.graph.types import GraphTraversalDirection
from tests.unit.src.streambuild.compiler.compile.helpers import compile_logical_project
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_pipeline_file,
)
from tests.unit.src.streambuild.compiler.discovery.helpers import write_project_toml
from tests.unit.src.streambuild.compiler.graph._test_types import (
    CrossModeRelationshipTestCase,
    FilteredClosureTestCase,
    GraphCycleTestCase,
    NonTerminalViewGraphTestCase,
    TypedProjectGraphTestCase,
    ViewAuxiliaryReferenceTestCase,
    ViewGraphTestCase,
)
from tests.unit.src.streambuild.compiler.graph.helpers import (
    build_cyclic_graph_project,
    build_nonterminal_view_graph_project,
    build_terminal_view_graph_project,
    build_typed_graph_project,
    logical_key,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TypedProjectGraphTestCase(
            description="types logical dependencies and orders keys stably",
            expected_ordered_names=(
                "orders",
                "cleaned",
                "lookup",
                "mutable_rates",
                "enriched",
            ),
            expected_enriched_edges=(
                ("cleaned", "driving_input"),
                ("lookup", "reference"),
                ("mutable_rates", "mutable_reference"),
            ),
            expected_lookup_downstream_edges=(("enriched", "reference"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compiled_project_when_building_graph_then_types_and_orders_dependencies(
    test_case: TypedProjectGraphTestCase,
) -> None:
    graph: ProjectGraph = build_project_graph_from_compiled_project(
        project=build_typed_graph_project()
    )
    enriched_edges: tuple[DependencyEdge, ...] = graph.upstream_edges_by_key[
        logical_key("enriched")
    ]
    lookup_edges: tuple[DependencyEdge, ...] = graph.downstream_edges_by_key[logical_key("lookup")]

    assert tuple(key.name for key in graph.ordered_keys) == test_case.expected_ordered_names
    assert tuple((edge.upstream_key.name, edge.edge_type) for edge in enriched_edges) == (
        test_case.expected_enriched_edges
    )
    assert tuple((edge.downstream_key.name, edge.edge_type) for edge in lookup_edges) == (
        test_case.expected_lookup_downstream_edges
    )
    assert isinstance(graph.upstream_edges_by_key, MappingProxyType)
    assert isinstance(graph.downstream_edges_by_key, MappingProxyType)


@pytest.mark.parametrize(
    "test_case",
    [
        FilteredClosureTestCase(
            description="separates execution closure from driving-only replay traversal",
            expected_all_downstream_names=("lookup", "enriched"),
            expected_driving_downstream_names=("lookup",),
            expected_all_upstream_names=(
                "orders",
                "cleaned",
                "lookup",
                "mutable_rates",
                "enriched",
            ),
            expected_driving_upstream_names=("orders", "cleaned", "enriched"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_typed_side_refs_when_collecting_closure_then_filters_by_edge_type(
    test_case: FilteredClosureTestCase,
) -> None:
    graph: ProjectGraph = build_project_graph_from_compiled_project(
        project=build_typed_graph_project()
    )

    assert (
        tuple(
            key.name
            for key in collect_reachable_keys(
                graph=graph,
                root_keys=frozenset({logical_key("lookup")}),
                direction=GraphTraversalDirection.DOWNSTREAM,
                edge_types=ALL_DEPENDENCY_EDGE_TYPES,
            )
        )
        == test_case.expected_all_downstream_names
    )
    assert (
        tuple(
            key.name
            for key in collect_reachable_keys(
                graph=graph,
                root_keys=frozenset({logical_key("lookup")}),
                direction=GraphTraversalDirection.DOWNSTREAM,
                edge_types=DRIVING_DEPENDENCY_EDGE_TYPES,
            )
        )
        == test_case.expected_driving_downstream_names
    )
    assert (
        tuple(
            key.name
            for key in collect_reachable_keys(
                graph=graph,
                root_keys=frozenset({logical_key("enriched")}),
                direction=GraphTraversalDirection.UPSTREAM,
                edge_types=ALL_DEPENDENCY_EDGE_TYPES,
            )
        )
        == test_case.expected_all_upstream_names
    )
    assert (
        tuple(
            key.name
            for key in collect_reachable_keys(
                graph=graph,
                root_keys=frozenset({logical_key("enriched")}),
                direction=GraphTraversalDirection.UPSTREAM,
                edge_types=DRIVING_DEPENDENCY_EDGE_TYPES,
            )
        )
        == test_case.expected_driving_upstream_names
    )


@pytest.mark.parametrize(
    "test_case",
    [
        GraphCycleTestCase(
            description="rejects a logical model dependency cycle deterministically",
            expected_error_fragment=(
                "Dependency cycle detected involving: model:alpha, model:beta"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cyclic_models_when_building_graph_then_raises_contextual_error(
    test_case: GraphCycleTestCase,
) -> None:
    with pytest.raises(GraphInputError, match=test_case.expected_error_fragment):
        build_project_graph_from_compiled_project(project=build_cyclic_graph_project())


@pytest.mark.parametrize(
    "test_case",
    [
        ViewGraphTestCase(
            description="adds every view upstream as an ordinary reference dependency",
            expected_upstream_edges=(
                ("lookup", "reference"),
                ("orders", "reference"),
            ),
            expected_downstream_edges=(("summary", "reference"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multi_upstream_terminal_view_when_building_graph_then_adds_reference_edges(
    test_case: ViewGraphTestCase,
) -> None:
    graph: ProjectGraph = build_project_graph_from_compiled_project(
        project=build_terminal_view_graph_project()
    )

    assert (
        tuple(
            (edge.upstream_key.name, edge.edge_type)
            for edge in graph.upstream_edges_by_key[logical_key("summary")]
        )
        == test_case.expected_upstream_edges
    )
    assert (
        tuple(
            (edge.downstream_key.name, edge.edge_type)
            for edge in graph.downstream_edges_by_key[logical_key("lookup")]
        )
        == test_case.expected_downstream_edges
    )


@pytest.mark.parametrize(
    "test_case",
    [
        NonTerminalViewGraphTestCase(
            description="rejects a view with a downstream side-reference model project-wide",
            expected_error_fragment=(
                "View model 'summary' must be terminal; referenced by downstream "
                r"model\(s\): consumer"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_view_with_downstream_model_when_building_graph_then_rejects_nonterminal_view(
    test_case: NonTerminalViewGraphTestCase,
) -> None:
    with pytest.raises(GraphInputError, match=test_case.expected_error_fragment):
        build_project_graph_from_compiled_project(project=build_nonterminal_view_graph_project())


@pytest.mark.parametrize(
    "test_case",
    [
        CrossModeRelationshipTestCase(
            description="rejects a direct model consumed by a virtual pipeline",
            upstream_mode="direct",
            downstream_mode="virtual",
            expected_error_fragment="Relations between direct and virtual",
        ),
        CrossModeRelationshipTestCase(
            description="rejects a virtual model consumed by a direct pipeline",
            upstream_mode="virtual",
            downstream_mode="direct",
            expected_error_fragment="Relations between direct and virtual",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cross_mode_relationship_when_building_graph_then_it_is_rejected_symmetrically(
    test_case: CrossModeRelationshipTestCase,
    tmp_path: Path,
) -> None:
    write_project_toml(
        project_dir=tmp_path,
        contents='name = "test"\ndefault_target = "test"\n[targets.test]\n',
    )
    write_pipeline_file(
        tmp_path / "sources" / "orders.yml",
        """
        sources:
          - name: orders
            kind: kafka
            broker_list: kafka:9092
            topic: source.orders
            replay_boundary: {mode: offsets}
        """,
    )
    write_pipeline_file(
        tmp_path / "pipelines" / "upstream" / "pipeline.toml",
        f'mode = "{test_case.upstream_mode}"',
    )
    write_pipeline_file(
        tmp_path / "pipelines" / "upstream" / "alpha.sql",
        'MODEL (order_by ["order_id"]); '
        'SELECT order_id::UInt64 AS order_id FROM __source("orders")',
    )
    write_pipeline_file(
        tmp_path / "pipelines" / "downstream" / "pipeline.toml",
        f'mode = "{test_case.downstream_mode}"',
    )
    write_pipeline_file(
        tmp_path / "pipelines" / "downstream" / "beta.sql",
        'MODEL (order_by ["order_id"]); SELECT order_id::UInt64 AS order_id FROM __ref("alpha")',
    )
    project: CompiledProject = compile_logical_project(tmp_path)

    with pytest.raises(GraphInputError, match=test_case.expected_error_fragment):
        build_project_graph_from_compiled_project(project=project)


@pytest.mark.parametrize(
    "test_case",
    [
        ViewAuxiliaryReferenceTestCase(
            description="allows SQL tests and audits to target a source-less terminal view",
            expected_test_case_count=1,
            expected_audit_count=1,
            expected_graph_names=("answer",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_terminal_view_auxiliaries_when_building_graph_then_excludes_auxiliary_edges(
    test_case: ViewAuxiliaryReferenceTestCase,
    tmp_path: Path,
) -> None:
    write_project_toml(
        project_dir=tmp_path,
        contents='name = "test"\ndefault_target = "test"\n[targets.test]\n',
    )
    write_pipeline_file(
        tmp_path / "pipelines" / "views" / "answer.sql",
        "MODEL (kind view); SELECT 1::UInt8 AS value",
    )
    write_pipeline_file(
        tmp_path / "tests" / "answer.sql",
        """
        TEST (name "answer test");
        WITH
          __source__orders AS (SELECT 1::UInt8 AS value),
          __expected__answer AS (SELECT 1::UInt8 AS value)
        SELECT 1
        """,
    )
    write_pipeline_file(
        tmp_path / "audits" / "answer.sql",
        """
        AUDIT (name "answer audit");
        SELECT value FROM __ref("answer") WHERE value = 0
        """,
    )
    project: CompiledProject = compile_logical_project(tmp_path)

    graph: ProjectGraph = build_project_graph_from_compiled_project(project=project)

    assert len(project.test_cases) == test_case.expected_test_case_count
    assert len(project.audits) == test_case.expected_audit_count
    assert tuple(key.name for key in graph.ordered_keys) == test_case.expected_graph_names
