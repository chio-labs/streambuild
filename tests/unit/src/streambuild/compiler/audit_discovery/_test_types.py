from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoverSqlAuditsTestCase:
    description: str
    relative_file_path: str
    file_contents: str
    expected_audit_names: tuple[str | None, ...]
    expected_referenced_model_names: tuple[tuple[str, ...], ...]
    expected_severities: tuple[str, ...]
    expected_descriptions: tuple[str | None, ...]


@dataclass(frozen=True)
class DiscoverSqlAuditsErrorTestCase:
    description: str
    relative_file_path: str
    file_contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class DiscoverSqlAuditsWithMacrosTestCase:
    description: str
    macro_file_contents: str
    audit_file_contents: str
    expected_query_fragment: str


@dataclass(frozen=True)
class DiscoverGenericSqlAuditsTestCase:
    description: str
    definition_name: str
    definition_file_contents: str
    schema_file_contents: str
    expected_name: str
    expected_query_fragments: tuple[str, ...]
    expected_referenced_model_names: tuple[str, ...]


@dataclass(frozen=True)
class DiscoverGenericSqlAuditsErrorTestCase:
    description: str
    definition_file_contents: str
    expected_error_fragment: str
