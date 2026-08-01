from dataclasses import dataclass


@dataclass(frozen=True)
class ParseModelSqlHeaderTestCase:
    description: str
    contents: str
    expected_header_values: dict[str, object]
    expected_query: str


@dataclass(frozen=True)
class ParseModelSqlHeaderErrorTestCase:
    description: str
    contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class InferTransformSourceErrorTestCase:
    description: str
    query: str
    expected_error_fragment: str


@dataclass(frozen=True)
class LoadTransformFromSqlFileTestCase:
    description: str
    macro_file_contents: str
    model_file_contents: str
    expected_query_fragment: str


@dataclass(frozen=True)
class LoadModelKindTestCase:
    description: str
    contents: str
    expected_step_type: type[object]
    expected_relation_name: str | None
    expected_has_engine: bool
