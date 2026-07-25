import json
from dataclasses import replace

from streambuild.cli.commands.main.audit.main import run_audit
from streambuild.cli.commands.main.audit_backfill.main import run_audit_backfill
from streambuild.cli.commands.main.backfill.main import run_backfill
from streambuild.cli.commands.main.compile.main import run_compile
from streambuild.cli.commands.main.discover import run_discover
from streambuild.cli.commands.main.doctor import run_doctor
from streambuild.cli.commands.main.entry.models import CliEntrypointHandlers
from streambuild.cli.commands.main.janitor.main import run_janitor
from streambuild.cli.commands.main.plan.main import run_plan
from streambuild.cli.commands.main.publish.main import run_publish
from streambuild.cli.commands.main.reconcile.main import run_reconcile
from streambuild.cli.commands.main.repair_active_view import run_repair_active_view
from streambuild.cli.commands.main.test.main import run_test


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
