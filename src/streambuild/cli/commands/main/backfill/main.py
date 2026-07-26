"""CLI command for staged backfill execution."""

import sys
from pathlib import Path

from streambuild.cli.commands.main.backfill._helpers.preview import build_backfill_preview_context
from streambuild.cli.commands.main.backfill._helpers.rendering import render_backfill_result
from streambuild.cli.commands.main.backfill.models import BackfillPreviewContext
from streambuild.cli.commands.main.shared._helpers.plan_rendering import render_plan_result
from streambuild.cli.commands.main.shared._helpers.timestamps import (
    convert_utc_timestamp_for_clickhouse,
    normalize_cli_start_time,
)
from streambuild.cli.commands.main.shared.constants import AFFIRMATIVE_RESPONSES
from streambuild.cli.commands.main.shared.exceptions import CliUserError
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.executor.backfill.main import execute_backfill
from streambuild.executor.backfill.models import BackfillBootstrapRequest, BackfillExecutionResult
from streambuild.integrations.clickhouse.client import ClickHouseClient


def run_backfill(
    *,
    pipelines_root: Path,
    database: str | None,
    metadata_database: str | None,
    selectors: tuple[str, ...],
    deployment_id: str | None,
    full_refresh: bool,
    start_time: str | None,
    json_output: bool,
    verbose: bool,
    auto_approve: bool,
    client: ClickHouseClient,
) -> int:
    """Execute a staged backfill and print the runtime result payload."""

    if json_output and not auto_approve:
        print("--json requires --auto-approve for backfill", file=sys.stderr)
        return 1
    if full_refresh and start_time is not None:
        print("--full-refresh cannot be combined with --start-time", file=sys.stderr)
        return 1
    if (full_refresh or start_time is not None) and not selectors:
        required_flag: str = "--full-refresh" if full_refresh else "--start-time"
        print(f"{required_flag} requires at least one --select", file=sys.stderr)
        return 1
    normalized_start_time: str | None = None
    if start_time is not None:
        try:
            normalized_start_time = convert_utc_timestamp_for_clickhouse(
                client=client,
                utc_timestamp=normalize_cli_start_time(start_time),
            )
        except (CliUserError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1

    try:
        preview_context: BackfillPreviewContext = build_backfill_preview_context(
            pipelines_root=pipelines_root,
            database=database,
            metadata_database=metadata_database,
            selectors=selectors,
            deployment_id=deployment_id,
            full_refresh=full_refresh,
            start_time=normalized_start_time,
            client=client,
        )
    except (CliUserError, TransformSqlContractError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

    if not json_output:
        print(
            render_plan_result(
                plan=preview_context.plan,
                desired_state=preview_context.desired_state,
                database=preview_context.resolved_database,
                json_output=False,
                verbose=verbose,
            )
        )
    if not auto_approve and not _confirm_backfill():
        print("Backfill cancelled.")
        return 1

    result: BackfillExecutionResult = execute_backfill(
        request=BackfillBootstrapRequest(
            desired_state=preview_context.desired_state,
            default_database=preview_context.resolved_database,
            metadata_database=preview_context.resolved_metadata_database,
            replay_lineage_mode=preview_context.replay_lineage_mode,
            deployment_id=deployment_id,
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
            json_output=json_output,
        )
    )
    return 0


def _confirm_backfill() -> bool:
    response: str = input("Proceed with backfill? [y/N] ").strip().lower()
    return response in AFFIRMATIVE_RESPONSES
