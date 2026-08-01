"""Atomic publication for one disposable connected plan artifact."""

import os
import tempfile
from pathlib import Path

from streambuild.cli.workflow_artifacts.types import WorkflowArtifactOwner


def publish_plan_artifact(*, target_dir: Path, owner: WorkflowArtifactOwner, contents: str) -> None:
    """Atomically replace a complete connected plan without making it state."""

    owner_dir: Path = target_dir / "run" / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    descriptor: int
    staged_name: str
    descriptor, staged_name = tempfile.mkstemp(prefix=".plan-staging-", dir=owner_dir)
    staged_path: Path = Path(staged_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as staged_file:
            _ = staged_file.write(contents)
            staged_file.flush()
            os.fsync(staged_file.fileno())
        os.replace(staged_path, owner_dir / "plan.json")
    finally:
        if staged_path.exists():
            staged_path.unlink()
