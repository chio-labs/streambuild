from dataclasses import dataclass


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
    expected_driving_input: str
    expected_source_kind: str


@dataclass(frozen=True)
class FailingAnalysisTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class StateFieldTestCase:
    description: str
    expected_source_freshness: str
    expected_model_freshness: str
    expected_model_lag_seconds: float
    expected_model_ownership: str
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


@dataclass(frozen=True)
class ChecksRunTestCase:
    description: str
    kind: str
    name: str
    expected_status: int
    expected_passed: bool
