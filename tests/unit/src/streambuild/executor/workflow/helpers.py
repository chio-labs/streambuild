from streambuild.executor.workflow.models import BuildWorkflow, WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowMode, WorkflowPhase


def build_test_workflow(*, plan_json: str) -> BuildWorkflow:
    return BuildWorkflow(
        mode=WorkflowMode.DIRECT,
        plan_json=plan_json,
        statements=(
            WarehouseStatement(
                sequence=1,
                step_id="check_ready",
                phase=WorkflowPhase.PREFLIGHT,
                intent=StatementIntent.ASSERTION,
                sql="SELECT 1;",
            ),
            WarehouseStatement(
                sequence=2,
                step_id="insert_event",
                phase=WorkflowPhase.REALIZATION,
                intent=StatementIntent.MUTATION,
                sql="INSERT INTO events VALUES (1);",
            ),
        ),
    )
