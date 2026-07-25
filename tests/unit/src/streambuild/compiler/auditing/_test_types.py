from dataclasses import dataclass


@dataclass(frozen=True)
class ValidateSqlAuditsErrorTestCase:
    description: str
    audit_file_contents: str
    expected_error_fragment: str
    generic_definition_file_contents: str | None = None
    schema_file_contents: str | None = None


@dataclass(frozen=True)
class ValidateSqlAuditsTestCase:
    description: str
    audit_file_contents: str
    expected_referenced_model_names: tuple[str, ...]
    expected_severity: str
    generic_definition_file_contents: str | None = None
    schema_file_contents: str | None = None
    expected_name: str | None = None
