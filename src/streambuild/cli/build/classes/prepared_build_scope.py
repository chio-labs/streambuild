"""Resolve and validate exact logical scopes for one prepared build."""

from __future__ import annotations

import json
import os
from typing import cast

from streambuild.cli.build.constants import (
    EXPECTED_BUILD_PIPELINE_SCOPE_ENV_VAR,
    EXPECTED_BUILD_READ_SCOPE_ENV_VAR,
    EXPECTED_BUILD_WRITE_SCOPE_ENV_VAR,
)
from streambuild.cli.build.models import (
    DirectWorkflowPreparation,
    MixedWorkflowPreparation,
    VirtualWorkflowPreparation,
)
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.observability.main.logical_resource_identities import (
    logical_resource_identities,
)


def _prepared_logical_scopes(
    preparation: DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return exact write and read identities from a connected preparation."""

    writes: set[str] = set()
    reads: set[str] = set()
    direct: DirectWorkflowPreparation | None = (
        preparation.direct
        if isinstance(preparation, MixedWorkflowPreparation)
        else preparation
        if isinstance(preparation, DirectWorkflowPreparation)
        else None
    )
    if direct is not None:
        writes.update(logical_resource_identities(direct.preview.plan.execution_scope))
        reads.update(
            logical_resource_identities(
                tuple(item.key for item in direct.preview.plan.prerequisite_scope)
            )
        )
    virtual: VirtualWorkflowPreparation | None = (
        preparation.virtual
        if isinstance(preparation, MixedWorkflowPreparation)
        else preparation
        if isinstance(preparation, VirtualWorkflowPreparation)
        else None
    )
    if virtual is not None:
        writes.update(logical_resource_identities(virtual.preview.run_execution_scope))
        reads.update(logical_resource_identities(virtual.preview.run_context_scope))
    return frozenset(writes), frozenset(reads)


def _validate_expected_prepared_logical_scopes(
    *,
    preparation: DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation,
    analysis: CompileAnalysis,
) -> None:
    """Abort when a dev-server child replans to a scope that was not authorized."""

    raw_writes: str | None = os.environ.get(EXPECTED_BUILD_WRITE_SCOPE_ENV_VAR)
    raw_reads: str | None = os.environ.get(EXPECTED_BUILD_READ_SCOPE_ENV_VAR)
    raw_pipelines: str | None = os.environ.get(EXPECTED_BUILD_PIPELINE_SCOPE_ENV_VAR)
    if raw_writes is None and raw_reads is None and raw_pipelines is None:
        return
    if raw_writes is None or raw_reads is None or raw_pipelines is None:
        raise CliUserError("Authorized build scope is incomplete; re-plan the build")
    expected_writes: frozenset[str] = _scope_from_json(raw_writes)
    expected_reads: frozenset[str] = _scope_from_json(raw_reads)
    expected_pipelines: frozenset[str] = _scope_from_json(raw_pipelines)
    actual_writes, actual_reads = _prepared_logical_scopes(preparation)
    actual_pipelines: frozenset[str] = _prepared_pipeline_scope(
        preparation=preparation,
        analysis=analysis,
    )
    if (actual_writes, actual_reads, actual_pipelines) != (
        expected_writes,
        expected_reads,
        expected_pipelines,
    ):
        raise CliUserError(
            "Build scope changed after server authorization; review and start the plan again"
        )


def _prepared_pipeline_scope(
    *,
    preparation: DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation,
    analysis: CompileAnalysis,
) -> frozenset[str]:
    keys: set[LogicalResourceKey] = set()
    direct: DirectWorkflowPreparation | None = (
        preparation.direct
        if isinstance(preparation, MixedWorkflowPreparation)
        else preparation
        if isinstance(preparation, DirectWorkflowPreparation)
        else None
    )
    if direct is not None:
        keys.update(direct.preview.plan.execution_scope)
        keys.update(item.key for item in direct.preview.plan.prerequisite_scope)
    virtual: VirtualWorkflowPreparation | None = (
        preparation.virtual
        if isinstance(preparation, MixedWorkflowPreparation)
        else preparation
        if isinstance(preparation, VirtualWorkflowPreparation)
        else None
    )
    if virtual is not None:
        keys.update(virtual.preview.run_execution_scope)
        keys.update(virtual.preview.run_context_scope)
    pipeline_by_key: dict[LogicalResourceKey, str] = {
        model.key: model.pipeline_name for model in analysis.compiled_project.models
    }
    return frozenset(
        f"{key.resource_type}:{key.name}={pipeline_by_key[key]}"
        for key in keys
        if key in pipeline_by_key
    )


def _scope_from_json(value: str) -> frozenset[str]:
    try:
        parsed: object = json.loads(value)
    except ValueError as error:
        raise CliUserError("Authorized build scope is invalid; re-plan the build") from error
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise CliUserError("Authorized build scope is invalid; re-plan the build")
    return frozenset(cast("list[str]", parsed))


class PreparedBuildScope:
    """Resolve and validate the exact logical scope of a prepared build."""

    @staticmethod
    def resolve(
        preparation: (
            DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation
        ),
    ) -> tuple[frozenset[str], frozenset[str]]:
        return _prepared_logical_scopes(preparation)

    @staticmethod
    def validate_expected(
        *,
        preparation: (
            DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation
        ),
        analysis: CompileAnalysis,
    ) -> None:
        _validate_expected_prepared_logical_scopes(
            preparation=preparation,
            analysis=analysis,
        )

    @staticmethod
    def pipeline_scope(
        *,
        preparation: (
            DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation
        ),
        analysis: CompileAnalysis,
    ) -> frozenset[str]:
        return _prepared_pipeline_scope(preparation=preparation, analysis=analysis)
