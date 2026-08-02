"""Expose virtual bootstrap workflow projection to preservation tests."""

from streambuild.executor.backfill._helpers.workflow import (
    build_virtual_bootstrap_workflow as _build_virtual_bootstrap_workflow,
)
from streambuild.executor.workflow.models import BuildWorkflow


def build_virtual_bootstrap_workflow(*, workflow: BuildWorkflow) -> BuildWorkflow:
    """Return the mutation prefix corresponding to candidate bootstrap."""

    return _build_virtual_bootstrap_workflow(workflow=workflow)
