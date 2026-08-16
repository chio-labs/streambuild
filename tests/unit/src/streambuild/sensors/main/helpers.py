from pathlib import Path
from textwrap import dedent

QUALITY_SENSOR_SOURCE: str = """
from streambuild.events import AuditCompleted
from streambuild.sensors import event_sensor


@event_sensor(on=AuditCompleted)
def quality_alerts(ctx):
    \"\"\"Alert on audit transitions.\"\"\"
"""

PROVIDER_SOURCE: str = """
from streambuild.providers import Provider


class OpsSlack(Provider):
    webhook_url: str = "https://hooks.example.invalid/ops"
"""

UNSUPPORTED_EVENT_SENSOR_SOURCE: str = """
from streambuild.sensors import event_sensor


class HomemadeEvent:
    pass


@event_sensor(on=HomemadeEvent)
def homemade(ctx):
    \"\"\"React to a non-catalog event.\"\"\"
"""


def write_project_files(*, project_dir: Path, files: tuple[tuple[str, str], ...]) -> None:
    for relative_path, contents in files:
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(contents).strip() + "\n", encoding="utf-8")
