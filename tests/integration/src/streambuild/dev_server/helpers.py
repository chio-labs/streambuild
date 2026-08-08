from pathlib import Path
from threading import Barrier
from typing import cast

from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.dev_server.classes.audit_scheduler import AuditScheduler
from tests.integration.src.streambuild.cli.helpers import write_audit_project_files
from tests.unit.src.streambuild.compiler.audit_discovery.helpers import write_sql_audit_file
from tests.unit.src.streambuild.compiler.discovery.helpers import write_project_toml


def write_scheduled_audit_project(
    *,
    project_dir: Path,
    database: str,
    severity: str = "warning",
    audit_query: str = (
        'SELECT order_id, line_total FROM __ref("order_items") '
        "WHERE sleep(0.05) = 0 AND line_total < 0"
    ),
) -> LoadedProject:
    write_audit_project_files(project_dir)
    write_project_toml(
        project_dir=project_dir,
        contents=f"""
        name = "scheduled_audit_integration"
        default_target = "test"

        [defaults.audits]
        severity = "warning"
        every = "1h"
        warmup = "0s"

        [targets.test]
        database = "{database}"

        [targets.test.audit_scheduler]
        enabled = true
        """,
    )
    write_sql_audit_file(
        project_dir / "audits" / "singular" / "order_events" / "negative_line_totals.sql",
        f"""
        AUDIT (
          name "scheduled negative line totals",
          severity {severity},
        );

        {audit_query}
        """,
    )
    return cast(LoadedProject, load_project_input_for_path(path=project_dir))


def tick_after_barrier(scheduler: AuditScheduler, start_barrier: Barrier) -> int:
    start_barrier.wait()
    return scheduler.tick()
