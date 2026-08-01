"""Workflow artifact ownership types."""

from enum import StrEnum


class WorkflowArtifactOwner(StrEnum):
    """Connected commands that own isolated visibility artifacts."""

    PLAN = "plan"
    BUILD = "build"
