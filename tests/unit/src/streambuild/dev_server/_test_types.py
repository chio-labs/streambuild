from collections.abc import Callable
from dataclasses import dataclass

from streambuild.compiler.compile.models import CompiledModel
from streambuild.dev_server.types import RunPresentationStatus


@dataclass(frozen=True)
class DevRefactorTestCase:
    description: str
    expected_value: object


@dataclass(frozen=True)
class CompileOutcomeTestCase:
    description: str
    break_compile: bool
    expected_state: str
    expected_has_analysis: bool


@dataclass(frozen=True)
class StatusEndpointTestCase:
    description: str
    break_compile: bool
    expected_state: str
    expected_warehouse_connected: bool


@dataclass(frozen=True)
class DefinitionsFieldTestCase:
    description: str
    expected_model_name: str
    expected_model_description: str
    expected_column_description: str
    expected_anchor: str
    expected_audit_name: str
    expected_audit_file_suffix: str
    expected_audit_generic_name: str
    expected_driving_input: str
    expected_source_kind: str
    expected_managed_ddl_fragment: str


@dataclass(frozen=True)
class FailingAnalysisTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class StateFieldTestCase:
    description: str
    fingerprint_status: str
    definition_hash_builder: Callable[[CompiledModel], str]
    identity_metadata_builder: Callable[[CompiledModel], str]
    expected_source_freshness: str
    expected_model_freshness: str
    expected_model_lag_seconds: float
    expected_drift_reasons: tuple[str, ...]
    expected_source_rows_per_second: float
    expected_partition_max_offset: int
    expected_bucket_count: int


@dataclass(frozen=True)
class PlanEndpointTestCase:
    description: str
    selectors: tuple[str, ...]
    expected_status: int
    expected_entry_names: tuple[str, ...]
    expected_command: str
    expected_replay_root_rows: tuple[int | None, ...]
    expected_sql_changes: tuple[str, ...]


@dataclass(frozen=True)
class ChecksStatusTestCase:
    description: str
    expected_name: str
    expected_status: str
    expected_failure_count: int
    expected_completed_at: str


@dataclass(frozen=True)
class RunEventsFeedTestCase:
    description: str
    invocation_id: str
    expected_event_kinds: tuple[str, ...]
    expected_written_rows: int


@dataclass(frozen=True)
class ChecksRunTestCase:
    description: str
    kind: str
    name: str
    expected_status: int
    expected_passed: bool


@dataclass(frozen=True)
class StaticAssetsPresenceTestCase:
    description: str
    expected_present: bool


@dataclass(frozen=True)
class SpaFallbackTestCase:
    description: str
    request_path: str
    expected_body_fragment: str


@dataclass(frozen=True)
class ReplayCountQueryTestCase:
    description: str
    start_time: str | None
    expected_query: str


@dataclass(frozen=True)
class ReplayTimeColumnTestCase:
    description: str
    boundary_mode: str
    expected_column: str


@dataclass(frozen=True)
class RunStatusDerivationTestCase:
    description: str
    terminal_outcome: str | None
    completed_event_outcome: str | None
    signal_age_seconds: int
    expected_status: RunPresentationStatus


@dataclass(frozen=True)
class RunDetailHistoryTestCase:
    description: str
    invocation_id: str
    expected_status: str
