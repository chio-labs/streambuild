import argparse
import json
from pathlib import Path
from typing import Any


def build_cli_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="stb",
        description="Declarative, versioned streaming data pipelines for ClickHouse.",
    )
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(
        dest="command", required=True
    )

    discover_parser: argparse.ArgumentParser = subparsers.add_parser(
        "discover",
        help="List discovered pipelines in a project",
        description="Scan the project directory and list all discovered pipelines.",
    )
    discover_parser.add_argument(
        "--project-dir",
        type=Path,
        help="Path to the project root containing pipelines/",
    )

    compile_parser: argparse.ArgumentParser = subparsers.add_parser(
        "compile",
        help="Compile pipelines into resolved SQL and ClickHouse DDL",
        description=(
            "Compile all pipeline models into resolved SQL, CREATE TABLE statements, "
            "CREATE MATERIALIZED VIEW statements, and a numbered workflow."
        ),
    )
    compile_parser.add_argument(
        "--project-dir",
        type=Path,
        help="Path to the project root containing pipelines/",
    )
    compile_parser.add_argument(
        "--target-dir",
        type=Path,
        help="Replace the project-level target/ artifact root",
    )

    test_parser: argparse.ArgumentParser = subparsers.add_parser(
        "test",
        help="Execute SQL-native model tests against ClickHouse",
        description=(
            "Discover SQL-native tests under tests/, assemble their dependency chain, "
            "and execute them against ClickHouse."
        ),
    )
    _add_project_dir_arg(parser=test_parser)
    _add_clickhouse_args(parser=test_parser)
    _add_select_args(test_parser)
    test_parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional test files or directories to run",
    )
    test_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show all diff rows for failing tests",
    )
    test_parser.add_argument(
        "--target-dir",
        type=Path,
        help="Replace the project-level target/ artifact root",
    )

    plan_parser: argparse.ArgumentParser = subparsers.add_parser(
        "plan",
        help="Preview what would change without making any modifications",
        description=(
            "Compare SQL models against the current state in ClickHouse and show "
            "what would change. No modifications are made."
        ),
    )
    _add_project_dir_arg(parser=plan_parser)
    _add_clickhouse_args(parser=plan_parser)
    _add_select_args(plan_parser)
    plan_parser.add_argument(
        "--deployment-id",
        help="Use a specific virtual deployment ID for exact workflow inspection",
    )
    plan_parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Force a full refresh of selected models (requires --select)",
    )
    plan_parser.add_argument(
        "--start-time",
        help="Replay from a specific time, e.g. '2026-04-17T18:00:00' (requires --select)",
    )
    plan_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the plan as JSON",
    )
    plan_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show full schema diffs for changed models",
    )

    build_parser: argparse.ArgumentParser = _add_build_parser(subparsers=subparsers)

    audit_parser: argparse.ArgumentParser = subparsers.add_parser(
        "audit",
        help="Run SQL audits against live or staged data",
        description=(
            "Run user-defined SQL audits against published logical views, or use "
            "`stb audit deployment` to audit a staged deployment before publishing."
        ),
    )
    _add_project_dir_arg(parser=audit_parser)
    _add_clickhouse_args(parser=audit_parser)
    _add_select_args(audit_parser)
    audit_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    audit_subparsers: argparse._SubParsersAction[argparse.ArgumentParser] = (
        audit_parser.add_subparsers(dest="audit_command")
    )
    audit_deployment_parser: argparse.ArgumentParser = audit_subparsers.add_parser(
        "deployment",
        help="Audit a staged deployment",
        description=(
            "Compare staged shadow tables against active tables to verify the build "
            "produced correct results. If --deployment-id is omitted, lists available deployments."
        ),
    )
    _add_project_dir_arg(parser=audit_deployment_parser, suppress_default=True)
    _add_clickhouse_args(parser=audit_deployment_parser, suppress_default=True)
    audit_deployment_parser.add_argument(
        "--deployment-id",
        help="Deployment to audit (omit to list available deployments)",
    )
    audit_deployment_parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Output as JSON",
    )

    publish_parser: argparse.ArgumentParser = subparsers.add_parser(
        "publish",
        help="Replace stable views with staged table bindings",
        description=(
            "Publish a deployment by replacing logical view bindings one relation at a time "
            "and reporting adapter atomicity. If --deployment-id is omitted, lists available "
            "deployments."
        ),
    )
    _add_project_dir_arg(parser=publish_parser)
    _add_clickhouse_args(parser=publish_parser)
    publish_parser.add_argument(
        "--deployment-id",
        help="Deployment to publish (omit to list available deployments)",
    )
    publish_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    reconcile_parser: argparse.ArgumentParser = subparsers.add_parser(
        "reconcile",
        help="Reconcile live metadata baseline",
        description=(
            "Reconcile the live metadata baseline for managed pipelines. "
            "Use --apply to persist changes."
        ),
    )
    _add_project_dir_arg(parser=reconcile_parser)
    _add_clickhouse_args(parser=reconcile_parser)
    _add_select_args(reconcile_parser)
    reconcile_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    reconcile_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the reconciliation (dry-run by default)",
    )

    janitor_parser: argparse.ArgumentParser = subparsers.add_parser(
        "janitor",
        help="Clean up stale deployment artifacts",
        description=(
            "Identify and optionally remove stale shadow tables from previous deployments. "
            "Dry-run by default; use --apply to drop tables."
        ),
    )
    _add_project_dir_arg(parser=janitor_parser)
    _add_clickhouse_args(parser=janitor_parser)
    janitor_parser.add_argument(
        "--retention-days",
        type=int,
        default=7,
        help="Keep deployments newer than this many days (default: 7)",
    )
    janitor_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually drop stale tables (dry-run by default)",
    )
    janitor_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    doctor_parser: argparse.ArgumentParser = subparsers.add_parser(
        "doctor",
        help="Diagnose issues with active views and managed tables",
        description=(
            "Inspect the current state of managed tables in ClickHouse and report "
            "any issues with logical views, shadow tables, or deployment references."
        ),
    )
    _add_project_dir_arg(parser=doctor_parser)
    _add_clickhouse_args(parser=doctor_parser)

    repair_parser: argparse.ArgumentParser = subparsers.add_parser(
        "repair",
        help="Repair broken deployment state",
        description="Repair broken logical views or deployment references.",
    )
    repair_subparsers: argparse._SubParsersAction[argparse.ArgumentParser] = (
        repair_parser.add_subparsers(dest="repair_command", required=True)
    )
    repair_active_view_parser: argparse.ArgumentParser = repair_subparsers.add_parser(
        "active-view",
        help="Re-point a logical view at a specific deployment",
        description=(
            "Repair a broken logical view by re-pointing it at a specific "
            "deployment's shadow table."
        ),
    )
    _add_project_dir_arg(parser=repair_active_view_parser)
    _add_clickhouse_args(parser=repair_active_view_parser)
    repair_active_view_parser.add_argument(
        "--table",
        required=True,
        help="The logical table name to repair, e.g. tbl__orders",
    )
    repair_active_view_parser.add_argument(
        "--deployment-id",
        required=True,
        help="The deployment to point the view at",
    )
    _add_compilation_config_args_to_commands(
        discover_parser=discover_parser,
        compile_parser=compile_parser,
        test_parser=test_parser,
        plan_parser=plan_parser,
        build_parser=build_parser,
        audit_parser=audit_parser,
        audit_deployment_parser=audit_deployment_parser,
        reconcile_parser=reconcile_parser,
    )
    for lifecycle_parser in (
        publish_parser,
        janitor_parser,
        doctor_parser,
        repair_active_view_parser,
    ):
        _add_compilation_config_args(parser=lifecycle_parser)
    return parser


def _add_build_parser(
    *, subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]"
) -> argparse.ArgumentParser:
    build_parser: argparse.ArgumentParser = subparsers.add_parser(
        "build",
        help="Build selected models in the effective project mode",
        description=(
            "Build the selected downstream closure directly or as an isolated virtual deployment. "
            "Shows the connected plan and asks for confirmation before making changes."
        ),
    )
    _add_project_dir_arg(parser=build_parser)
    _add_clickhouse_args(parser=build_parser)
    _add_select_args(build_parser)
    build_parser.add_argument(
        "--deployment-id",
        help="Use a specific virtual deployment ID (auto-generated if omitted)",
    )
    build_parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Force a full refresh of selected virtual-environment models (requires --select)",
    )
    build_parser.add_argument(
        "--start-time",
        help="Replay selected virtual-environment models from a time (requires --select)",
    )
    build_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    build_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show full schema diffs for changed models",
    )
    build_parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip the confirmation prompt",
    )
    return build_parser


def _add_project_dir_arg(
    *, parser: argparse.ArgumentParser, suppress_default: bool = False
) -> None:
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=argparse.SUPPRESS if suppress_default else None,
        help="Path to the project root containing pipelines/",
    )


def _parse_cli_vars(value: str) -> dict[str, object]:
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(f"--vars must be valid JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("--vars must be a JSON object")
    return {str(key): item for key, item in parsed.items()}


def _add_compilation_config_args(
    *, parser: argparse.ArgumentParser, suppress_defaults: bool = False
) -> None:
    default_target: object = argparse.SUPPRESS if suppress_defaults else None
    default_variables: object = argparse.SUPPRESS if suppress_defaults else {}
    parser.add_argument("--target", default=default_target, help="Named project target to use")
    parser.add_argument(
        "--vars",
        type=_parse_cli_vars,
        default=default_variables,
        help="Project variable overrides as one JSON object",
    )


def _add_compilation_config_args_to_commands(
    *,
    discover_parser: argparse.ArgumentParser,
    compile_parser: argparse.ArgumentParser,
    test_parser: argparse.ArgumentParser,
    plan_parser: argparse.ArgumentParser,
    build_parser: argparse.ArgumentParser,
    audit_parser: argparse.ArgumentParser,
    audit_deployment_parser: argparse.ArgumentParser,
    reconcile_parser: argparse.ArgumentParser,
) -> None:
    command_parser: argparse.ArgumentParser
    for command_parser in (
        discover_parser,
        compile_parser,
        test_parser,
        plan_parser,
        build_parser,
        audit_parser,
        reconcile_parser,
    ):
        _add_compilation_config_args(parser=command_parser)
    _add_compilation_config_args(parser=audit_deployment_parser, suppress_defaults=True)


def _add_clickhouse_args(
    *, parser: argparse.ArgumentParser, suppress_default: bool = False
) -> None:
    default: object = argparse.SUPPRESS if suppress_default else None
    parser.add_argument("--host", default=default, help="ClickHouse host")
    parser.add_argument("--port", type=int, default=default, help="ClickHouse HTTP port")
    parser.add_argument("--username", default=default, help="ClickHouse username")
    parser.add_argument("--password", default=default, help="ClickHouse password")
    parser.add_argument("--database", default=default, help="Target ClickHouse database")


def _add_select_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--select",
        action="append",
        default=[],
        help=(
            "Select models or pipelines, e.g. --select daily_revenue "
            "or --select pipeline:order_events (repeatable)"
        ),
    )
