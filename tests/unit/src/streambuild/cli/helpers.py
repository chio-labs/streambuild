import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from streambuild.cli.audit.main._run_audit import run_audit
from streambuild.cli.audit_backfill.main._run_audit_backfill import run_audit_backfill
from streambuild.cli.backfill.main._run_backfill import run_backfill
from streambuild.cli.backfill.models import BackfillCommandOptions
from streambuild.cli.compile.main._run_compile import run_compile
from streambuild.cli.discover.main._run_discover import run_discover
from streambuild.cli.doctor.main._run_doctor import run_doctor
from streambuild.cli.entry.models import CliEntrypointHandlers
from streambuild.cli.janitor.main._run_janitor import run_janitor
from streambuild.cli.plan.main._run_plan import run_plan
from streambuild.cli.publish.main._run_publish import run_publish
from streambuild.cli.reconcile.main._run_reconcile import run_reconcile
from streambuild.cli.repair_active_view.main._run_repair_active_view import run_repair_active_view
from streambuild.cli.test.main._run_test import run_test


def normalize_json_output(output: str) -> str:
    parsed: object = json.loads(output)
    return json.dumps(parsed, sort_keys=True)


class FakeCliClickHouseClient:
    def close(self) -> None:
        return None


class BackfillCommandRunnerAdapter:
    def __init__(self, runner: Callable[..., int]) -> None:
        self._runner: Callable[..., int] = runner

    def __call__(self, *, options: BackfillCommandOptions, client: object) -> int:
        return self._runner(
            pipelines_root=options.pipelines_root,
            database=options.database,
            metadata_database=options.metadata_database,
            selectors=options.selectors,
            deployment_id=options.deployment_id,
            full_refresh=options.full_refresh,
            start_time=options.start_time,
            json_output=options.json_output,
            verbose=options.verbose,
            auto_approve=options.auto_approve,
            client=client,
        )


def handlers_with_overrides(**overrides: object) -> CliEntrypointHandlers:
    has_backfill_override: bool = "run_backfill" in overrides
    backfill_override: object = overrides.pop("run_backfill", run_backfill)
    backfill_handler: Callable[..., int] = {
        False: run_backfill,
        True: BackfillCommandRunnerAdapter(cast(Callable[..., int], backfill_override)),
    }[has_backfill_override]
    return replace(
        CliEntrypointHandlers(
            run_discover=run_discover,
            run_compile=run_compile,
            run_test=run_test,
            run_audit=run_audit,
            run_plan=run_plan,
            run_backfill=backfill_handler,
            run_audit_backfill=run_audit_backfill,
            run_publish=run_publish,
            run_reconcile=run_reconcile,
            run_janitor=run_janitor,
            run_doctor=run_doctor,
            run_repair_active_view=run_repair_active_view,
        ),
        **overrides,
    )


CLI_COMMAND_HANDLER_NAMES: dict[str, str] = {
    "audit backfill": "run_audit_backfill",
    "publish": "run_publish",
    "doctor": "run_doctor",
}

CLI_COMMAND_ARGV: dict[str, tuple[str, ...]] = {
    "audit backfill": ("stb", "audit", "backfill"),
    "publish": ("stb", "publish"),
    "doctor": ("stb", "doctor"),
}


def passthrough_output(output: str) -> str:
    """Return CLI output unchanged, for commands that print text rather than JSON."""

    return output


OUTPUT_NORMALIZERS: dict[bool, Callable[[str], str]] = {
    True: normalize_json_output,
    False: passthrough_output,
}
