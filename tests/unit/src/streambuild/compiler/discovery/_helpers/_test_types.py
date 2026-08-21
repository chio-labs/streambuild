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


@dataclass(frozen=True)
class LoadModelDescriptionTestCase:
    description: str
    contents: str
    expected_description: str | None


@dataclass(frozen=True)
class LoadModelExecutionSettingsTestCase:
    description: str
    contents: str
    expected_replay_settings: dict[str, str]


@dataclass(frozen=True)
class GlobalNameCollisionTestCase:
    description: str
    pipeline_name: str
    source_names: tuple[str, ...]
    model_names: tuple[str, ...]
    expected_error_fragment: str
