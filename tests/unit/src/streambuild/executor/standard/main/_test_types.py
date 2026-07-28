from dataclasses import dataclass


@dataclass(frozen=True)
class ExecuteStandardBuildTestCase:
    description: str
    selected_model_names: tuple[str, ...]
    expected_drop_statements: tuple[str, ...]
    expected_created_relation_names: tuple[str, ...]
    expected_replay_relations: tuple[tuple[str, str, str], ...]
    expected_replay_query_fragments: tuple[str, ...]
    expected_ownership_record_count: int


@dataclass(frozen=True)
class ReplayCoverageInputChangeTestCase:
    description: str
    persisted_driving_input_relation_name: str
    expected_error_fragment: str
