"""Register the single-request browser bootstrap endpoint."""

from pathlib import Path

from fastapi import FastAPI, Request

from streambuild.auth.classes.authentication_service import AuthenticationService
from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.main.build_browser_auth_payload import build_browser_auth_payload
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.payloads.definitions_payload import build_definitions_payload
from streambuild.dev_server._helpers.server.authorization_enforcement import (
    build_capabilities_payload,
)
from streambuild.dev_server._helpers.server.compile_runner import build_status_payload
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.classes.warehouse_runtime import WarehouseRuntime
from streambuild.dev_server.exceptions import ProjectNotCompiledError
from streambuild.dev_server.models import (
    CompileOutcome,
    DevExecutionContext,
    OperationAuthorizationContext,
)


def register_bootstrap_route(
    *,
    app: FastAPI,
    authentication: AuthenticationService,
    state: DevServerState,
    warehouse: WarehouseRuntime,
    project_dir: Path,
    execution_context: DevExecutionContext,
    control_store: ControlStore,
) -> FastAPI:
    """Attach one authenticated endpoint for the complete initial UI state."""

    authorization: OperationAuthorizationContext = OperationAuthorizationContext(
        store=control_store,
        project_dir=project_dir,
        selected_target=execution_context.selected_target,
    )

    def read_bootstrap(request: Request) -> dict[str, object]:
        outcome: CompileOutcome = state.current()
        analysis: CompileAnalysis | None
        definitions: dict[str, object] | None
        try:
            servable: CompileOutcome = state.current_servable_outcome()
            analysis = state.current_analysis()
            definitions = build_definitions_payload(
                analysis=analysis,
                version_key=servable.version_key,
            )
        except ProjectNotCompiledError:
            analysis = None
            definitions = None
        auth: dict[str, object] = build_browser_auth_payload(
            service=authentication,
            request=request,
        )
        auth["capabilities"] = build_capabilities_payload(
            analysis=analysis,
            request=request,
            context=authorization,
        )
        return {
            "auth": auth,
            "status": build_status_payload(
                outcome=outcome,
                warehouse_status=warehouse.status(),
            ),
            "definitions": definitions,
            "state": state.snapshot.held(),
        }

    app.get("/api/bootstrap")(read_bootstrap)
    return app
