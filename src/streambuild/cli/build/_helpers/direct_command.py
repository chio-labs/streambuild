"""Execute one confirmed direct-mode build command."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build._helpers.execution import execute_confirmed_direct_build
from streambuild.cli.build._helpers.rendering import (
    render_direct_build_json,
    render_direct_build_text,
)
from streambuild.cli.build.models import (
    BuildCommandOptions,
    DirectBuildPreviewContext,
    DirectWorkflowPreparation,
)
from streambuild.executor.auditing.models import SqlAuditRunResult
from streambuild.executor.direct.models import (
    DirectBuildExecutionResult,
    DirectBuildResult,
)


def execute_direct_build_command(
    *,
    preparation: DirectWorkflowPreparation,
    options: BuildCommandOptions,
    client: AdapterConnection,
) -> int:
    """Confirm, execute, and audit one prepared direct build."""

    execution: DirectBuildExecutionResult | None = execute_confirmed_direct_build(
        preparation=preparation,
        options=options,
        client=client,
    )
    if execution is None:
        return 1
    print(
        _rendered_result(
            options=options,
            preview=preparation.preview,
            result=execution.build_result,
            audit_result=execution.audit_result,
        )
    )
    return 1 if execution.audit_result.error_failure_count else 0


def _rendered_result(
    *,
    options: BuildCommandOptions,
    preview: DirectBuildPreviewContext,
    result: DirectBuildResult,
    audit_result: SqlAuditRunResult,
) -> str:
    if options.json_output:
        return render_direct_build_json(
            result=result,
            adapter_name=preview.adapter_name,
            audit_result=audit_result,
        )
    return render_direct_build_text(
        result=result,
        adapter_name=preview.adapter_name,
        audit_result=audit_result,
    )
