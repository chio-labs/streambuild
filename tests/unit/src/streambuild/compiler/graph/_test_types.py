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


@dataclass(frozen=True)
class ViewGraphTestCase:
    description: str
    expected_upstream_edges: tuple[tuple[str, str], ...]
    expected_downstream_edges: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class NonTerminalViewGraphTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ViewAuxiliaryReferenceTestCase:
    description: str
    expected_test_case_count: int
    expected_audit_count: int
    expected_graph_names: tuple[str, ...]


@dataclass(frozen=True)
class CrossModeRelationshipTestCase:
    description: str
    upstream_mode: str
    downstream_mode: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ModelReferenceScopeSuccessTestCase:
    description: str
    dependencies_toml: str
    upstream_pipeline: str
    downstream_pipeline: str
    downstream_query: str
    expected_model_name: str


@dataclass(frozen=True)
class ModelReferenceScopeErrorTestCase:
    description: str
    downstream_model_sql: str
    expected_error_fragment: str
