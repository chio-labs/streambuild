"""Build the target audit scheduler dry-run payload."""

from pathlib import Path

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.compiler.pipeline.models import CompileAnalysis
from sqltide.dev_server.classes.audit_schedule_calculator import AuditScheduleCalculator
from sqltide.dev_server.main._scheduler_enabled import scheduler_enabled


def build_audit_scheduler_payload(
    *,
    analysis: CompileAnalysis,
    connection: AdapterConnection,
    database: str,
    project_dir: Path,
) -> dict[str, object]:
    """Return current due-state preview without executing audit SQL."""

    calculator: AuditScheduleCalculator = AuditScheduleCalculator(
        analysis=analysis,
        connection=connection,
        database=database,
        project_dir=project_dir,
    )
    return calculator.build_payload(enabled=scheduler_enabled(analysis))
