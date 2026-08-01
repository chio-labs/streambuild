from dataclasses import dataclass


@dataclass(frozen=True)
class ExecuteDirectBuildTestCase:
    description: str
    selected_model_names: tuple[str, ...]
    expected_drop_statements: tuple[str, ...]
    expected_created_relation_names: tuple[str, ...]
    expected_realized_relation_names: tuple[str, ...]
    expected_replay_relations: tuple[tuple[str, str, str], ...]
    expected_replay_query_fragments: tuple[str, ...]
    expected_replay_written_rows: tuple[int | None, ...]
    expected_ownership_record_count: int


@dataclass(frozen=True)
class ReplayCoverageInputChangeTestCase:
    description: str
    persisted_driving_input_relation_name: str
    persisted_partition_column_name: str
    persisted_position_column_name: str
    persisted_timestamp_column_name: str
    expected_error_fragment: str


@dataclass(frozen=True)
class EmptyReplayNoOpTestCase:
    description: str
    expected_replay_result_count: int
    expected_preserved_coverage_count: int
