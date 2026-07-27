from dataclasses import dataclass


@dataclass(frozen=True)
class TypedProjectGraphTestCase:
    description: str
    expected_ordered_names: tuple[str, ...]
    expected_enriched_edges: tuple[tuple[str, str], ...]
    expected_lookup_downstream_edges: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class FilteredClosureTestCase:
    description: str
    expected_all_downstream_names: tuple[str, ...]
    expected_driving_downstream_names: tuple[str, ...]
    expected_all_upstream_names: tuple[str, ...]
    expected_driving_upstream_names: tuple[str, ...]


@dataclass(frozen=True)
class GraphCycleTestCase:
    description: str
    expected_error_fragment: str
