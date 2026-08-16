import time
from pathlib import Path
from textwrap import dedent

from streambuild.events import AuditCompleted
from streambuild.sensors import DefaultSensorStatus, SkipReason, event_sensor

QUALITY_SENSOR_SOURCE: str = """
from streambuild.events import AuditCompleted
from streambuild.sensors import DefaultSensorStatus, event_sensor


@event_sensor(on=AuditCompleted, default_status=DefaultSensorStatus.RUNNING)
def quality_alerts(ctx):
    \"\"\"Alert on audit transitions.

    Further details live here.
    \"\"\"
"""

LAG_SENSOR_SOURCE: str = """
from streambuild.sensors import polling_sensor


@polling_sensor(minimum_interval_seconds=60)
def kafka_lag_watch(ctx):
    \"\"\"Watch consumer lag.\"\"\"
"""


def write_project_files(*, project_dir: Path, files: tuple[tuple[str, str], ...]) -> None:
    for relative_path, contents in files:
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")


@event_sensor(on=AuditCompleted, default_status=DefaultSensorStatus.RUNNING)
def quiet_handler(ctx: object) -> None:
    """Succeed without output."""


@event_sensor(on=AuditCompleted, default_status=DefaultSensorStatus.RUNNING)
def skipping_handler(ctx: object) -> SkipReason:
    return SkipReason("nothing to do")


@event_sensor(on=AuditCompleted, default_status=DefaultSensorStatus.RUNNING)
def raising_handler(ctx: object) -> None:
    raise ValueError("bad webhook")


@event_sensor(
    on=AuditCompleted,
    default_status=DefaultSensorStatus.RUNNING,
    timeout_seconds=0.05,
)
def hanging_handler(ctx: object) -> None:
    time.sleep(0.5)
