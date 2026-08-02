"""Publish a workflow and return its execution capability."""

import hashlib
from pathlib import Path

from streambuild.cli.workflow_artifacts._helpers.build_publication import publish_workflow_artifact
from streambuild.cli.workflow_artifacts.types import WorkflowArtifactOwner
from streambuild.executor.workflow.models import BuildWorkflow, PublishedBuildWorkflow


def publish_build_workflow(*, target_dir: Path, workflow: BuildWorkflow) -> PublishedBuildWorkflow:
    """Publish exact workflow bytes before granting permission to execute them."""

    artifact_root: Path = publish_workflow_artifact(
        target_dir=target_dir,
        owner=WorkflowArtifactOwner.BUILD,
        workflow=workflow,
    )
    workflow_sql: str = "\n".join(statement.sql for statement in workflow.statements)
    return PublishedBuildWorkflow(
        workflow=workflow,
        artifact_root=artifact_root,
        workflow_sha256=hashlib.sha256(workflow_sql.encode("utf-8")).hexdigest(),
    )
