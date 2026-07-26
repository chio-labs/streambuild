import json
from collections.abc import Callable
from dataclasses import replace

from streambuild.cli.audit.main.run_audit import run_audit
from streambuild.cli.audit_backfill.main.run_audit_backfill import run_audit_backfill
from streambuild.cli.backfill.main.run_backfill import run_backfill
from streambuild.cli.compile.main.run_compile import run_compile
from streambuild.cli.discover.main.run_discover import run_discover
from streambuild.cli.doctor.main.run_doctor import run_doctor
from streambuild.cli.entry.models import CliEntrypointHandlers
from streambuild.cli.janitor.main.run_janitor import run_janitor
from streambuild.cli.plan.main.run_plan import run_plan
from streambuild.cli.publish.main.run_publish import run_publish
from streambuild.cli.reconcile.main.run_reconcile import run_reconcile
from streambuild.cli.repair_active_view.main.run_repair_active_view import run_repair_active_view
from streambuild.cli.test.main.run_test import run_test


def normalize_json_output(output: str) -> str:
    parsed: object = json.loads(output)
    return json.dumps(parsed, sort_keys=True)


class FakeCliClickHouseClient:
    def close(self) -> None:
        return None


def handlers_with_overrides(**overrides: object) -> CliEntrypointHandlers:
    return replace(
        CliEntrypointHandlers(
            run_discover=run_discover,
            run_compile=run_compile,
            run_test=run_test,
            run_audit=run_audit,
            run_plan=run_plan,
            run_backfill=run_backfill,
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
