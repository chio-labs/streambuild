from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceExtractionTestCase:
    description: str
    sql: str
    expected_references: tuple[tuple[str, str, str | None], ...]
    expected_source_slices: tuple[str, ...]
    expected_coordinates: tuple[tuple[int, int, int, int], ...]


@dataclass(frozen=True)
class ReferenceErrorTestCase:
    description: str
    sql: str
    expected_error_fragment: str
    expected_line: int
    expected_column: int


@dataclass(frozen=True)
class ReferenceParityTestCase:
    description: str
    sql: str
    expected_reference_count: int


@dataclass(frozen=True)
class CompilerReferenceDiagnosticTestCase:
    description: str
    sql: str
    source_path: str
    source_line: int
    source_column: int
    expected_location: tuple[str, int, int, int, int]
    expected_phase: str


@dataclass(frozen=True)
class RepositoryReferenceFixtureTestCase:
    description: str
    fixture_root: str
    expected_relative_paths: tuple[str, ...]
    expected_reference_name: str
    expected_replacement: str


@dataclass(frozen=True)
class ReferenceRewriteTestCase:
    description: str
    sql: str
    resolver: dict[str, str]
    expected_sql: str


@dataclass(frozen=True)
class ReferenceRewriteErrorTestCase:
    description: str
    sql: str
    resolver: dict[str, str]
    expected_error_fragment: str


@dataclass(frozen=True)
class PolyglotCallCountTestCase:
    description: str
    sql: str
    resolver: dict[str, str]
    expected_parse_calls: int
    expected_generate_calls: int


@dataclass(frozen=True)
class PolyglotInvocationCacheTestCase:
    description: str
    first_sql: str
    second_sql: str
    resolver: dict[str, str]
    expected_parse_calls: int
    expected_generate_calls: int


@dataclass(frozen=True)
class SqlAnalysisBoundaryTestCase:
    description: str
    forbidden_import: str
    expected_outside_import_paths: tuple[str, ...]
    expected_retired_path_exists: bool
    expected_dependency_spec: str
    expected_fallback_import_paths: tuple[str, ...]


@dataclass(frozen=True)
class ModelTypeAnalysisTestCase:
    description: str
    sql: str
    expected_columns: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ModelAggregateAnalysisTestCase:
    description: str
    sql: str
    engine: str
    expected_order_by: str
    expected_function_names: tuple[str, ...]
    expected_has_group_by: bool
    expected_engine_has_aggregate_semantics: bool
    expected_has_semantics: bool


@dataclass(frozen=True)
class ModelStorageAnalysisTestCase:
    description: str
    sql: str
    order_by: tuple[str, ...]
    partition_by: str | None
    ttl: str | None
    expected_storage_facts: tuple[tuple[str, str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class ModelResolutionTestCase:
    description: str
    sql: str
    resolver: dict[str, str]
    expected_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ModelReservedPlaceholderTestCase:
    description: str
    sql: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ModelCallCountTestCase:
    description: str
    sql: str
    resolver: dict[str, str]
    expected_parse_calls: int
    expected_parse_one_calls: int
    expected_analyze_calls: int
    expected_generate_calls: int


@dataclass(frozen=True)
class ModelLineageAnalysisTestCase:
    description: str
    sql: str
    expected_upstream: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class ModelAnalysisOrderingTestCase:
    description: str
    sql_by_model: tuple[str, ...]
    expected_output_names: tuple[str, ...]
