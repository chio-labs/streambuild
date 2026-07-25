from dataclasses import dataclass

from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.executor.backfill.models import BackfillExecutionResult
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


@dataclass(frozen=True)
class StartTimeReplayScenarioResult:
    connection_settings: ClickHouseConnectionSettings
    database: str
    compiled_pipeline: CompiledPipeline
    start_time_result: BackfillExecutionResult
    converted_start_time: str
    shadow_rows: tuple[tuple[str, str], ...]
