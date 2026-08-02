"""Atomic publication of one complete disposable workflow artifact."""

import os
import shutil
import tempfile
from pathlib import Path

from streambuild.cli.workflow_artifacts.types import WorkflowArtifactOwner
from streambuild.executor.workflow.models import BuildWorkflow, WarehouseStatement


def publish_workflow_artifact(
    *, target_dir: Path, owner: WorkflowArtifactOwner, workflow: BuildWorkflow
) -> Path:
    """Replace one owner's complete artifact directory without exposing partial files."""

    run_dir: Path = target_dir / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    staged_root: Path = Path(tempfile.mkdtemp(prefix=f".{owner}-staging-", dir=run_dir))
    artifact_root: Path = run_dir / owner
    previous_root: Path = run_dir / f".{owner}-previous"
    try:
        _write_staged_workflow(staged_root=staged_root, workflow=workflow)
        if previous_root.exists():
            shutil.rmtree(previous_root)
        if artifact_root.exists():
            os.replace(artifact_root, previous_root)
        try:
            os.replace(staged_root, artifact_root)
        except OSError:
            if previous_root.exists():
                os.replace(previous_root, artifact_root)
            raise
        if previous_root.exists():
            shutil.rmtree(previous_root)
        return artifact_root
    finally:
        if staged_root.exists():
            shutil.rmtree(staged_root)


def _write_staged_workflow(*, staged_root: Path, workflow: BuildWorkflow) -> None:
    steps_root: Path = staged_root / "steps"
    steps_root.mkdir()
    (staged_root / "plan.json").write_text(workflow.plan_json, encoding="utf-8")
    statement: WarehouseStatement
    for statement in workflow.statements:
        filename: str = f"{statement.sequence:04d}_{statement.step_id}.sql"
        (steps_root / filename).write_text(statement.sql, encoding="utf-8")
    workflow_sql: str = "\n".join(statement.sql for statement in workflow.statements)
    (staged_root / "workflow.sql").write_text(workflow_sql, encoding="utf-8")
