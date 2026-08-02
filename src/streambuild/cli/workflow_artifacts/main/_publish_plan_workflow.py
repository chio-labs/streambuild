"""Publish one complete workflow as disposable plan visibility evidence."""

from pathlib import Path

from streambuild.cli.workflow_artifacts._helpers.build_publication import publish_workflow_artifact
from streambuild.cli.workflow_artifacts.types import WorkflowArtifactOwner
from streambuild.executor.workflow.models import BuildWorkflow


def publish_plan_workflow(*, target_dir: Path, workflow: BuildWorkflow) -> None:
    """Publish exact plan workflow bytes without granting execution capability."""

    _ = publish_workflow_artifact(
        target_dir=target_dir,
        owner=WorkflowArtifactOwner.PLAN,
        workflow=workflow,
    )
