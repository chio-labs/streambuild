"""CLI command for deployment publish."""

import sys

from clickhouse_connect.driver.exceptions import DatabaseError, OperationalError

from streambuild.cli.publish._helpers.candidates import (
    candidate_root_names,
    enrich_candidates,
)
from streambuild.cli.publish._helpers.rendering import render_publish_result
from streambuild.cli.shared.main._deployment_candidates import (
    render_ambiguous_deployment_message,
    render_no_deployment_candidates_message,
)
from streambuild.cli.shared.main._errors import render_expected_clickhouse_error
from streambuild.clickhouse.inspect.main import inspect_managed_table_state
from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.executor.audit_backfill.models import AuditDeploymentCandidate
from streambuild.executor.publish._helpers.resolution import build_publish_deployment_candidates
from streambuild.executor.publish.main import execute_publish
from streambuild.executor.publish.models import PublishRequest, PublishResult
from streambuild.integrations.clickhouse.client import ClickHouseClient


def run_publish(
    *,
    database: str,
    metadata_database: str | None,
    deployment_id: str | None,
    json_output: bool,
    client: ClickHouseClient,
) -> int:
    """Publish a staged deployment and print the result payload."""

    resolved_metadata_database: str = metadata_database or database
    try:
        if deployment_id is None:
            candidates: tuple[AuditDeploymentCandidate, ...] = build_publish_deployment_candidates(
                client=client,
                metadata_database=resolved_metadata_database,
                default_database=database,
            )
            if not candidates:
                print(
                    render_no_deployment_candidates_message(
                        command_name="publish",
                        database=database,
                    ),
                    file=sys.stderr,
                )
                return 1
            if len(candidates) > 1:
                inspected_state: InspectedManagedTableState = inspect_managed_table_state(
                    client=client,
                    database=database,
                )
                print(
                    render_ambiguous_deployment_message(
                        command_name="publish",
                        database=database,
                        root_names=candidate_root_names(inspected_state),
                        candidates=enrich_candidates(
                            client=client,
                            metadata_database=resolved_metadata_database,
                            candidates=candidates,
                        ),
                    ),
                    file=sys.stderr,
                )
                return 1
        result: PublishResult = execute_publish(
            request=PublishRequest(
                deployment_id=deployment_id,
                metadata_database=resolved_metadata_database,
                default_database=database,
            ),
            client=client,
        )
    except (DatabaseError, OperationalError) as error:
        rendered_error: str | None = render_expected_clickhouse_error(
            command_name="publish",
            database=database,
            error=error,
        )
        if rendered_error is not None:
            print(rendered_error, file=sys.stderr)
            return 1
        raise
    print(
        render_publish_result(
            result=result,
            database=database,
            json_output=json_output,
        )
    )
    return 0
