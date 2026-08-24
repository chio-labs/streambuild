from unittest.mock import MagicMock

from streambuild.cli.entry.models import CliEntrypointHandlers


def handlers_with_destruction(*, run_destruction: MagicMock) -> CliEntrypointHandlers:
    no_op: MagicMock = MagicMock(return_value=0)
    return CliEntrypointHandlers(
        run_discover=no_op,
        run_compile=no_op,
        run_test=no_op,
        run_audit=no_op,
        run_plan=no_op,
        run_build=no_op,
        run_destruction=run_destruction,
        run_deployment_diff=no_op,
        run_deployment_list=no_op,
        run_deployment_show=no_op,
        run_deployment_audit=no_op,
        run_deployment_promote=no_op,
        run_deployment_rollback=no_op,
        run_reconcile=no_op,
        run_janitor=no_op,
        run_doctor=no_op,
        run_repair_active_view=no_op,
        run_dev=no_op,
    )
