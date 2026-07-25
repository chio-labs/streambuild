from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CliBackfillIntegrationTestCase:
    description: str
    pipelines_root: Path
    selectors: tuple[str, ...]
    full_refresh: bool
    start_time: str | None
    json_output: bool
    verbose: bool
    auto_approve: bool
    prompt_response: str | None
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    expected_error_fragments: tuple[str, ...]
    expected_deployment_status_rows: tuple[tuple[str, ...], ...]
    expected_selected_root_names: tuple[str, ...] = ()
    expected_runtime_execution_modes: tuple[tuple[str, str | None], ...] = ()


@dataclass(frozen=True)
class CliTestCommandIntegrationTestCase:
    description: str
    selectors: tuple[str, ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliAuditCommandIntegrationTestCase:
    description: str
    selectors: tuple[str, ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliAuditBackfillCommandIntegrationTestCase:
    description: str
    expected_exit_code: int
    expected_quality_check_count: int
    expected_assessment: str
    expected_failing_row_count: int
