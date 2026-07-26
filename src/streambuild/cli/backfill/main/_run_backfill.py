"""CLI command for staged backfill execution."""

import sys

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.backfill._helpers.preview import build_backfill_preview_context
from streambuild.cli.backfill.main.render_backfill_result import render_backfill_result
from streambuild.cli.backfill.models import BackfillCommandOptions, BackfillPreviewContext
from streambuild.cli.entry.constants import AFFIRMATIVE_RESPONSES
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.main._normalize_cli_start_time import normalize_cli_start_time
from streambuild.cli.plan.main.render_plan_result import render_plan_result
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.executor.backfill.main.execute_backfill import execute_backfill
from streambuild.executor.backfill.models import BackfillBootstrapRequest, BackfillExecutionResult


def run_backfill(
    *,
    options: BackfillCommandOptions,
    client: AdapterConnection,
) -> int:
    """Execute a staged backfill and print the runtime result payload."""

    if options.json_output and not options.auto_approve:
        print("--json requires --auto-approve for backfill", file=sys.stderr)
        return 1
    if options.full_refresh and options.start_time is not None:
        print("--full-refresh cannot be combined with --start-time", file=sys.stderr)
        return 1
    if (options.full_refresh or options.start_time is not None) and not options.selectors:
        required_flag: str = "--full-refresh" if options.full_refresh else "--start-time"
        print(f"{required_flag} requires at least one --select", file=sys.stderr)
        return 1
    normalized_utc_start_time: str | None = None
    if options.start_time is not None:
        try:
            normalized_utc_start_time = normalize_cli_start_time(options.start_time)
        except (CliUserError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1

    try:
        preview_context: BackfillPreviewContext = build_backfill_preview_context(
            pipelines_root=options.pipelines_root,
            database=options.database,
            metadata_database=options.metadata_database,
            selectors=options.selectors,
            deployment_id=options.deployment_id,
            full_refresh=options.full_refresh,
            start_time_utc=normalized_utc_start_time,
            client=client,
        )
    except (CliUserError, TransformSqlContractError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

    if not options.json_output:
        print(
            render_plan_result(
                plan=preview_context.plan,
                desired_state=preview_context.desired_state,
                database=preview_context.resolved_database,
                json_output=False,
                verbose=options.verbose,
            )
        )
    if not options.auto_approve and not _confirm_backfill():
        print("Backfill cancelled.")
        return 1

    result: BackfillExecutionResult = execute_backfill(
        request=BackfillBootstrapRequest(
            desired_state=preview_context.desired_state,
            default_database=preview_context.resolved_database,
            metadata_database=preview_context.resolved_metadata_database,
            replay_lineage_mode=preview_context.replay_lineage_mode,
            deployment_id=options.deployment_id,
            full_refresh_keys=preview_context.full_refresh_keys,
            start_time_keys=preview_context.start_time_keys,
            start_time=preview_context.start_time,
        ),
        client=client,
    )

    print(
        render_backfill_result(
            result=result,
            database=preview_context.resolved_database,
            json_output=options.json_output,
        )
    )
    return 0


def _confirm_backfill() -> bool:
    response: str = input("Proceed with backfill? [y/N] ").strip().lower()
    return response in AFFIRMATIVE_RESPONSES
