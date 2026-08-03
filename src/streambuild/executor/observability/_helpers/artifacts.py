"""Publish exact terminal observation SQL as non-authoritative runtime evidence."""

from pathlib import Path

from streambuild.adapter.models import AdapterInvocationRecord
from streambuild.executor.workflow.models import WarehouseStatement


def publish_observation_artifact(
    *, invocation: AdapterInvocationRecord, statements: tuple[WarehouseStatement, ...]
) -> None:
    """Write combined and numbered SQL bytes before observation execution."""

    artifact_root: Path = (
        Path(invocation.project_identity)
        / "target"
        / "run"
        / "observations"
        / invocation.invocation_id
    )
    steps_root: Path = artifact_root / "steps"
    steps_root.mkdir(parents=True, exist_ok=True)
    statement: WarehouseStatement
    for statement in statements:
        (steps_root / f"{statement.sequence:04d}_{statement.step_id}.sql").write_text(
            statement.sql,
            encoding="utf-8",
        )
    (artifact_root / "workflow.sql").write_text(
        "\n".join(statement.sql for statement in statements),
        encoding="utf-8",
    )
