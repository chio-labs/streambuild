"""Publish one connected command's deterministic plan artifact."""

from pathlib import Path

from streambuild.cli.workflow_artifacts._helpers.publication import publish_plan_artifact
from streambuild.cli.workflow_artifacts.types import WorkflowArtifactOwner


def write_plan_artifact(*, target_dir: Path, owner: WorkflowArtifactOwner, contents: str) -> None:
    """Atomically replace only the requesting command's plan artifact."""

    publish_plan_artifact(target_dir=target_dir, owner=owner, contents=contents)
