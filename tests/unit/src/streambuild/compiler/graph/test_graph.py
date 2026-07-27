from types import MappingProxyType

import pytest

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
from tests.unit.src.streambuild.compiler.graph._test_types import (
    FilteredClosureTestCase,
    GraphCycleTestCase,
    TypedProjectGraphTestCase,
)
from tests.unit.src.streambuild.compiler.graph.helpers import (
    build_cyclic_graph_project,
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
