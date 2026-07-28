from __future__ import annotations

import argparse
from pathlib import Path
from shutil import copytree
from typing import cast

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterAuthenticationError
from streambuild.adapter.models import AdapterConnectionConfig
from streambuild.cli.entry._helpers.entrypoint import (
    resolve_adapter_connection_config,
)
from streambuild.cli.entry._helpers.parser import build_cli_parser
from streambuild.cli.entry.main.main import _main_with_dependencies, main
from streambuild.cli.entry.models import CliEntrypointHandlers
from tests.unit.src.streambuild.cli._test_types import (
    CliAuditBackfillProjectContextTestCase,
    CliCompileArtifactsTestCase,
    CliJanitorApplyFlagTestCase,
    CliMainEnvResolutionTestCase,
    CliMainErrorTestCase,
    CliMainIntegrationTestCase,
    CliMainJsonFlagTestCase,
    CliMainJsonTestCase,
    CliNestedAuditOptionsTestCase,
    CliProjectConnectionResolutionTestCase,
    CliProjectDefaultsTestCase,
    CliReconcileForwardingTestCase,
    CliSelectorForwardingTestCase,
)
from tests.unit.src.streambuild.cli.helpers import (
    CLI_COMMAND_ARGV,
    CLI_COMMAND_HANDLER_NAMES,
    OUTPUT_NORMALIZERS,
    FakeCliClickHouseClient,
    handlers_with_overrides,
    normalize_json_output,
    write_cli_compilation_project,
)


class PrintingCommandRunner:
    def __init__(self, output: str) -> None:
        self.output: str = output

    def __call__(self, *_args: object, **_kwargs: object) -> int:
        print(self.output)
        return 0


class RecordingCommandRunner:
    def __init__(self) -> None:
        self.pipelines_root: Path | None = None
        self.kwargs: dict[str, object] = {}

    def __call__(self, *_args: object, pipelines_root: Path | None = None, **kwargs: object) -> int:
        self.pipelines_root = pipelines_root
        self.kwargs.update(kwargs)
        return 0


class RecordingAuditBackfillCommandRunner:
    def __init__(self) -> None:
        self.pipelines_root: Path | None = None
        self.kwargs: dict[str, object] = {}

    def __call__(self, pipelines_root: Path | None, **kwargs: object) -> int:
        self.pipelines_root = pipelines_root
        self.kwargs.update(kwargs)
        return 0


class FailingCommandRunner:
    def __init__(self, error: Exception) -> None:
        self.error: Exception = error

    def __call__(self, *_args: object, **_kwargs: object) -> int:
        raise self.error


class PlanCommandRunner:
    def __call__(self, *_args: object, **kwargs: object) -> int:
        if kwargs.get("json_output"):
            print(
                "{\n"
                '  "steps": ['
                '{"phase": "create", "target_key": {"name": "tbl__orders_enriched"}}],\n'
                '  "rebuild_subtrees": '
                '[{"upstream_boundary_key": {"name": "raw__orders"}}],\n'
                '  "warnings": []\n}'
            )
            return 0
        print(
            "Plan Ready\n"
            "Database: analytics\n"
            "Subtrees to rebuild: 1\n"
            "Planned steps: 1\n\n"
            "Subtrees:\n"
            "Subtree 1\n"
            "[replay start] raw__orders\n"
            "└── [live target] tbl__orders_enriched\n\n"
            "Prepared staged objects\n"
            "- table: tbl__orders_enriched\n\n"
            "Workflow\n"
            "- prepare staged objects for subtree rooted at raw__orders\n"
            "- backfill from raw__orders\n"
            "- audit staged tbl__orders_enriched\n"
            "- publish tbl__orders_enriched\n\n"
            "Warnings:\n"
            "- none"
        )
        return 0


@pytest.mark.parametrize(
    "test_case",
    [
        CliMainJsonTestCase(
            description="prints discovered pipeline names as json",
            argv=("stb", "discover", "--project-dir", "tests/fixtures/basic_project"),
            expected_exit_code=0,
            expected_output_fragments=("orders",),
        ),
        CliMainJsonTestCase(
            description="prints backfill payload as json",
            argv=(
                "stb",
                "backfill",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
            ),
            expected_exit_code=0,
            expected_output_fragments=(
                '"deployment_id": "20260410T000000Z_ab12cd"',
                '"replay_strategy": "create_from_scratch"',
            ),
            handler_name="run_backfill",
            handler_output="{\n"
            '  "deployment_id": "20260410T000000Z_ab12cd",\n'
            '  "boundary_time": "2026-04-10 00:00:00.000",\n'
            '  "root_reports": [{"name": "tbl__orders_enriched", '
            '"replay_strategy": "create_from_scratch"}]\n'
            "}",
        ),
        CliMainJsonTestCase(
            description="prints audit backfill payload as json",
            argv=(
                "stb",
                "audit",
                "backfill",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
            ),
            expected_exit_code=0,
            expected_output_fragments=(
                '"deployment_status": "backfilling"',
                '"assessment": "ready"',
                '"name": "tbl__orders_enriched"',
            ),
            handler_name="run_audit_backfill",
            handler_output="{\n"
            '  "deployment_id": "20260410T000000Z_ab12cd",\n'
            '  "deployment_status": "backfilling",\n'
            '  "assessment": "ready",\n'
            '  "warning_codes": [],\n'
            '  "root_results": [{"name": "tbl__orders_enriched"}]\n'
            "}",
        ),
        CliMainJsonTestCase(
            description="prints live audit payload as json",
            argv=(
                "stb",
                "audit",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
            ),
            expected_exit_code=0,
            expected_output_fragments=(
                '"error_failure_count": 0',
                '"warning_failure_count": 1',
                '"severity": "warning"',
            ),
            handler_name="run_audit",
            handler_output="{\n"
            '  "error_failure_count": 0,\n'
            '  "warning_failure_count": 1,\n'
            '  "audit_results": [{"severity": "warning"}]\n'
            "}",
        ),
        CliMainJsonTestCase(
            description="prints publish payload as json",
            argv=(
                "stb",
                "publish",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
            ),
            expected_exit_code=0,
            expected_output_fragments=(
                '"deployment_id": "20260410T000000Z_ab12cd"',
                '"view_name": "tbl__orders_enriched"',
                '"target_table_name": "tbl__orders_enriched__20260410T000000Z_ab12cd"',
            ),
            handler_name="run_publish",
            handler_output="{\n"
            '  "deployment_id": "20260410T000000Z_ab12cd",\n'
            '  "published_views": [{"view_name": "tbl__orders_enriched", '
            '"target_table_name": "tbl__orders_enriched__20260410T000000Z_ab12cd"}]\n'
            "}",
        ),
        CliMainJsonTestCase(
            description="prints doctor payload as json",
            argv=(
                "stb",
                "doctor",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
            ),
            expected_exit_code=0,
            expected_output_fragments=(
                '"table_name": "tbl__orders_enriched"',
                '"state_kind": "logical_view_missing"',
            ),
            handler_name="run_doctor",
            handler_output="{\n"
            '  "active_views": [{"table_name": "tbl__orders_enriched", '
            '"state_kind": "logical_view_missing"}]\n'
            "}",
        ),
        CliMainJsonTestCase(
            description="prints repair active-view payload as json",
            argv=(
                "stb",
                "repair",
                "active-view",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
                "--table",
                "tbl__orders_enriched",
                "--deployment-id",
                "20260410T000000Z_ab12cd",
            ),
            expected_exit_code=0,
            expected_output_fragments=(
                '"table_name": "tbl__orders_enriched"',
                '"target_table_name": "tbl__orders_enriched__20260410T000000Z_ab12cd"',
            ),
            handler_name="run_repair_active_view",
            handler_output="{\n"
            '  "table_name": "tbl__orders_enriched",\n'
            '  "target_table_name": "tbl__orders_enriched__20260410T000000Z_ab12cd"\n'
            "}",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cli_args_when_running_main_then_it_prints_expected_json(
    test_case: CliMainJsonTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())
    override_candidates: dict[str | None, PrintingCommandRunner] = {
        test_case.handler_name: PrintingCommandRunner(test_case.handler_output)
    }
    _ = override_candidates.pop(None, None)
    overrides: dict[str, PrintingCommandRunner] = cast(
        dict[str, PrintingCommandRunner], override_candidates
    )
    handlers: CliEntrypointHandlers = handlers_with_overrides(**overrides)

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )
    captured_output: str = capsys.readouterr().out
    normalized_output: str = normalize_json_output(captured_output)

    assert exit_code == test_case.expected_exit_code
    for expected_fragment in test_case.expected_output_fragments:
        assert expected_fragment in normalized_output


@pytest.mark.parametrize(
    "test_case",
    [
        CliAuditBackfillProjectContextTestCase(
            description="resolves project context for audit backfill",
            argv=(
                "stb",
                "audit",
                "backfill",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
            ),
            expected_exit_code=0,
            expected_project_dir_name="basic_project",
            expected_pipelines_root_name="pipelines",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_audit_backfill_cli_args_when_running_main_then_it_forwards_project_context(
    test_case: CliAuditBackfillProjectContextTestCase,
) -> None:
    command_runner: RecordingAuditBackfillCommandRunner = RecordingAuditBackfillCommandRunner()

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers_with_overrides(run_audit_backfill=command_runner),
        adapter_connection=cast(AdapterConnection, FakeCliClickHouseClient()),
    )

    assert exit_code == test_case.expected_exit_code
    assert command_runner.pipelines_root is not None
    assert command_runner.pipelines_root.name == test_case.expected_pipelines_root_name
    assert command_runner.kwargs["project_dir"] is not None
    assert (
        cast(Path, command_runner.kwargs["project_dir"]).name == test_case.expected_project_dir_name
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CliMainErrorTestCase(
            description="prints a clear transform sql contract error to stderr",
            argv=("stb", "compile", "--project-dir", "BROKEN_PIPELINES_ROOT"),
            expected_exit_code=1,
            expected_error_fragments=(
                "orders_enriched",
                "outermost SELECT",
                "UNION or UNION ALL",
                "expr::Type AS name",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_transform_sql_when_running_compile_then_it_prints_a_clear_error(
    test_case: CliMainErrorTestCase,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    pipeline_root: Path = tmp_path / "pipelines"
    write_cli_compilation_project(
        project_root=tmp_path,
        model_sql="""
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
        );

        SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
        UNION ALL
        SELECT CAST(order_id AS UInt64) AS order_id FROM replay_orders
        """,
    )
    argv_paths: dict[str, str] = {"BROKEN_PIPELINES_ROOT": str(pipeline_root)}
    argv: list[str] = [argv_paths.get(part, part) for part in test_case.argv]

    exit_code: int = main(argv)
    captured_error: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    for expected_fragment in test_case.expected_error_fragments:
        assert expected_fragment in captured_error


@pytest.mark.parametrize(
    "test_case",
    [
        CliMainIntegrationTestCase(
            description="prints deployment plan summary as text",
            argv=(
                "stb",
                "plan",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
            ),
            expected_exit_code=0,
            expected_output_fragments=(
                "Plan Ready",
                "Subtrees to rebuild: 1",
                "[replay start] raw__orders",
                "[live target] tbl__orders_enriched",
            ),
        ),
        CliMainIntegrationTestCase(
            description="prints deployment plan payload as json when requested",
            argv=(
                "stb",
                "plan",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
                "--json",
            ),
            expected_exit_code=0,
            expected_output_fragments=(
                '"phase": "create"',
                '"name": "tbl__orders_enriched"',
                '"upstream_boundary_key":',
            ),
            expects_json_output=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cli_args_when_running_plan_then_it_prints_expected_output(
    test_case: CliMainIntegrationTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_plan=PlanCommandRunner())
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )
    captured_output: str = capsys.readouterr().out
    normalized_output: str = OUTPUT_NORMALIZERS[test_case.expects_json_output](captured_output)

    assert exit_code == test_case.expected_exit_code
    for expected_fragment in test_case.expected_output_fragments:
        assert expected_fragment in normalized_output


@pytest.mark.parametrize(
    "test_case",
    [
        CliMainEnvResolutionTestCase(
            description="uses clickhouse env vars for plan defaults",
            argv=("stb", "plan", "--project-dir", "tests/fixtures/basic_project"),
            env_vars={
                "STREAMBUILD_CLICKHOUSE_HOST": "localhost",
                "STREAMBUILD_CLICKHOUSE_PORT": "8123",
                "STREAMBUILD_CLICKHOUSE_USERNAME": "streambuild",
                "STREAMBUILD_CLICKHOUSE_PASSWORD": "streambuild",
            },
            expected_exit_code=0,
            expected_kwargs={
                "database": "analytics",
                "selectors": (),
                "full_refresh": False,
                "start_time": None,
                "json_output": False,
                "verbose": False,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clickhouse_env_vars_when_running_plan_then_it_uses_env_defaults(
    test_case: CliMainEnvResolutionTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_plan=runner)
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        environment=test_case.env_vars,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_kwargs.items() <= runner.kwargs.items()
    assert runner.kwargs["client"] is clickhouse_client


@pytest.mark.parametrize(
    "test_case",
    [
        CliProjectDefaultsTestCase(
            description="uses project yaml database default for plan",
            command_name="plan",
            expected_database="analytics",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_yaml_when_running_plan_then_it_uses_project_database_defaults(
    test_case: CliProjectDefaultsTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root: Path = tmp_path / "demo"
    write_cli_compilation_project(
        project_root=project_root,
        model_sql="""
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
        );

        SELECT order_id::UInt64 AS order_id FROM __ref("orders")
        """,
    )

    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_plan=runner)
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())
    monkeypatch.chdir(project_root)

    exit_code: int = _main_with_dependencies(
        argv=("stb", "plan"),
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )

    assert exit_code == 0
    assert {
        "database": test_case.expected_database,
        "selectors": (),
        "full_refresh": False,
        "start_time": None,
        "json_output": False,
        "verbose": False,
        "client": clickhouse_client,
    }.items() <= runner.kwargs.items()


@pytest.mark.parametrize(
    "test_case",
    [
        CliProjectDefaultsTestCase(
            description="uses project yaml database default for audit backfill",
            command_name="audit backfill",
            expected_database="analytics",
        ),
        CliProjectDefaultsTestCase(
            description="uses project yaml database default for publish",
            command_name="publish",
            expected_database="analytics",
        ),
        CliProjectDefaultsTestCase(
            description="uses project yaml database default for doctor",
            command_name="doctor",
            expected_database="analytics",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_yaml_when_running_runtime_command_then_it_uses_project_defaults(
    test_case: CliProjectDefaultsTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root: Path = tmp_path / "demo"
    write_cli_compilation_project(
        project_root=project_root,
        model_sql="""
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
        );

        SELECT order_id::UInt64 AS order_id FROM __ref("orders")
        """,
    )

    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(
        **{CLI_COMMAND_HANDLER_NAMES[test_case.command_name]: runner}
    )
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())
    monkeypatch.chdir(project_root)

    argv: tuple[str, ...] = CLI_COMMAND_ARGV[test_case.command_name]

    exit_code: int = _main_with_dependencies(
        argv=argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )

    assert exit_code == 0
    assert runner.kwargs["database"] == test_case.expected_database
    assert runner.kwargs["client"] == clickhouse_client


@pytest.mark.parametrize(
    "test_case",
    [
        CliProjectDefaultsTestCase(
            description="uses --project-dir for audit backfill",
            command_name="audit backfill",
            expected_database="analytics",
        ),
        CliProjectDefaultsTestCase(
            description="uses --project-dir for publish",
            command_name="publish",
            expected_database="analytics",
        ),
        CliProjectDefaultsTestCase(
            description="uses --project-dir for doctor",
            command_name="doctor",
            expected_database="analytics",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_dir_when_running_runtime_command_then_it_uses_project_defaults(
    test_case: CliProjectDefaultsTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root: Path = tmp_path / "demo"
    write_cli_compilation_project(
        project_root=project_root,
        model_sql="""
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
        );

        SELECT order_id::UInt64 AS order_id FROM __ref("orders")
        """,
    )

    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(
        **{CLI_COMMAND_HANDLER_NAMES[test_case.command_name]: runner}
    )
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())
    monkeypatch.chdir(tmp_path)

    argv: tuple[str, ...] = (
        *CLI_COMMAND_ARGV[test_case.command_name],
        "--project-dir",
        str(project_root),
    )

    exit_code: int = _main_with_dependencies(
        argv=argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )

    assert exit_code == 0
    assert runner.kwargs["database"] == test_case.expected_database
    assert runner.kwargs["client"] == clickhouse_client


@pytest.mark.parametrize(
    "test_case",
    [
        CliProjectConnectionResolutionTestCase(
            description="uses project clickhouse defaults when cli and env are absent",
            expected_project_connection=("localhost", 8123, "streambuild", "streambuild"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_clickhouse_defaults_when_resolving_connection_then_it_uses_them(
    test_case: CliProjectConnectionResolutionTestCase,
) -> None:
    project_connection: AdapterConnectionConfig = AdapterConnectionConfig(
        host=test_case.expected_project_connection[0],
        port=test_case.expected_project_connection[1],
        username=test_case.expected_project_connection[2],
        password=test_case.expected_project_connection[3],
    )

    resolved_connection: AdapterConnectionConfig = resolve_adapter_connection_config(
        host=None,
        port=None,
        username=None,
        password=None,
        project_connection=project_connection,
    )

    assert resolved_connection == AdapterConnectionConfig(
        host=test_case.expected_project_connection[0],
        port=test_case.expected_project_connection[1],
        username=test_case.expected_project_connection[2],
        password=test_case.expected_project_connection[3],
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CliMainJsonFlagTestCase(
            description="passes json flag through to plan command",
            argv=(
                "stb",
                "plan",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
                "--json",
            ),
            expected_exit_code=0,
            expected_json_output=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_json_flag_when_running_plan_then_it_passes_json_output_to_command(
    test_case: CliMainJsonFlagTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_plan=runner)
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )

    assert exit_code == test_case.expected_exit_code
    assert runner.kwargs["json_output"] is test_case.expected_json_output


@pytest.mark.parametrize(
    "test_case",
    [
        CliSelectorForwardingTestCase(
            description="passes selectors and full refresh through to plan command",
            argv=(
                "stb",
                "plan",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--select",
                "orders_enriched",
                "--select",
                "pipeline:orders",
                "--full-refresh",
            ),
            expected_exit_code=0,
            expected_selectors=("orders_enriched", "pipeline:orders"),
            expected_full_refresh=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selectors_when_running_plan_then_it_passes_selection_kwargs_to_command(
    test_case: CliSelectorForwardingTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_plan=runner)
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )

    assert exit_code == test_case.expected_exit_code
    assert runner.kwargs["selectors"] == test_case.expected_selectors
    assert runner.kwargs["full_refresh"] is test_case.expected_full_refresh


@pytest.mark.parametrize(
    "test_case",
    [
        CliJanitorApplyFlagTestCase(
            description="passes apply flag through to janitor command",
            argv=(
                "stb",
                "janitor",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
                "--apply",
            ),
            expected_exit_code=0,
            expected_apply=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_apply_flag_when_running_janitor_then_it_passes_apply_to_command(
    test_case: CliJanitorApplyFlagTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_janitor=runner)
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )

    assert exit_code == test_case.expected_exit_code
    assert runner.kwargs["apply"] is test_case.expected_apply
    assert "metadata_database" not in runner.kwargs


@pytest.mark.parametrize(
    "test_case",
    [
        CliMainErrorTestCase(
            description="prints command value errors without a traceback",
            argv=(
                "stb",
                "publish",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
            ),
            expected_exit_code=1,
            expected_error_fragments=(
                "Deployment 'dep_missing' has no staged physical tables to publish",
            ),
        ),
        CliMainErrorTestCase(
            description="renders clickhouse authentication errors without a traceback",
            argv=(
                "stb",
                "doctor",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
            ),
            expected_exit_code=1,
            expected_error_fragments=(
                "Doctor could not start",
                "ClickHouse rejected the supplied credentials",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_expected_command_errors_when_running_entrypoint_then_it_prints_clean_stderr(
    test_case: CliMainErrorTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    handlers: CliEntrypointHandlers = handlers_with_overrides(
        run_publish=FailingCommandRunner(
            ValueError("Deployment 'dep_missing' has no staged physical tables to publish")
        ),
        run_doctor=FailingCommandRunner(
            AdapterAuthenticationError(
                "Code: 516. DB::Exception: Authentication failed. (AUTHENTICATION_FAILED)"
            )
        ),
    )
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )
    captured_error: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert "Traceback" not in captured_error
    for expected_fragment in test_case.expected_error_fragments:
        assert expected_fragment in captured_error


@pytest.mark.parametrize(
    "test_case",
    [
        CliMainJsonFlagTestCase(
            description="passes json flag through to backfill command",
            argv=(
                "stb",
                "backfill",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--host",
                "localhost",
                "--port",
                "8123",
                "--username",
                "streambuild",
                "--password",
                "streambuild",
                "--database",
                "analytics",
                "--json",
            ),
            expected_exit_code=0,
            expected_json_output=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_json_flag_when_running_backfill_then_it_passes_json_output_to_command(
    test_case: CliMainJsonFlagTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_backfill=runner)
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )

    assert exit_code == test_case.expected_exit_code
    assert runner.kwargs["json_output"] is test_case.expected_json_output


@pytest.mark.parametrize(
    "test_case",
    [
        CliSelectorForwardingTestCase(
            description="passes selectors and full refresh through to backfill command",
            argv=(
                "stb",
                "backfill",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--select",
                "orders_enriched",
                "--full-refresh",
                "--auto-approve",
            ),
            expected_exit_code=0,
            expected_selectors=("orders_enriched",),
            expected_full_refresh=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selectors_when_running_backfill_then_it_passes_selection_kwargs_to_command(
    test_case: CliSelectorForwardingTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_backfill=runner)
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )

    assert exit_code == test_case.expected_exit_code
    assert runner.kwargs["selectors"] == test_case.expected_selectors
    assert runner.kwargs["full_refresh"] is test_case.expected_full_refresh


@pytest.mark.parametrize(
    "test_case",
    [
        CliReconcileForwardingTestCase(
            description="passes selectors, apply, and json flags through to reconcile command",
            argv=(
                "stb",
                "reconcile",
                "--project-dir",
                "tests/fixtures/basic_project",
                "--select",
                "orders_enriched",
                "--apply",
                "--json",
            ),
            expected_exit_code=0,
            expected_selectors=("orders_enriched",),
            expected_apply=True,
            expected_json_output=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reconcile_flags_when_running_reconcile_then_it_passes_kwargs_to_command(
    test_case: CliReconcileForwardingTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_reconcile=runner)
    clickhouse_client: AdapterConnection = cast(AdapterConnection, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        adapter_connection=clickhouse_client,
    )

    assert exit_code == test_case.expected_exit_code
    assert runner.kwargs["selectors"] == test_case.expected_selectors
    assert runner.kwargs["apply"] is test_case.expected_apply
    assert runner.kwargs["json_output"] is test_case.expected_json_output


@pytest.mark.parametrize(
    "test_case",
    [
        CliCompileArtifactsTestCase(
            description="writes compile artifacts to target layout",
            argv=(
                "stb",
                "compile",
                "--project-dir",
                ".",
                "--target-dir",
                "target_out",
            ),
            expected_exit_code=0,
            expected_output_fragments=("Wrote compile artifacts to", "Pipelines: 1", "Models: 1"),
            expected_written_files=(
                "target_out/manifest.json",
                "target_out/streambuild_dag.json",
                "target_out/compiled/models/orders/orders_enriched.sql",
                "target_out/compiled/resources/models/orders/orders_enriched.table.sql",
                "target_out/compiled/resources/models/orders/orders_enriched.mv.sql",
                "target_out/compiled/resources/sources/orders/kafka__orders.sql",
                "target_out/compiled/resources/sources/orders/raw__orders.sql",
                "target_out/compiled/resources/sources/orders/mv__orders.sql",
                "target_out/compiled/workflows/orders/steps/0001_kafka_table.sql",
                "target_out/compiled/workflows/orders/steps/0002_raw_table.sql",
                "target_out/compiled/workflows/orders/steps/0003_landing_mv.sql",
                "target_out/compiled/workflows/orders/steps/0010_orders_enriched.table.sql",
                "target_out/compiled/workflows/orders/steps/0011_orders_enriched.mv.sql",
                "target_out/compiled/workflows/orders/workflow.sql",
                "target_out/compiled/workflows/orders/workflow.json",
            ),
            expected_target_dir_name="target_out",
        ),
        CliCompileArtifactsTestCase(
            description="writes default target under project root",
            argv=(
                "stb",
                "compile",
                "--project-dir",
                ".",
            ),
            expected_exit_code=0,
            expected_output_fragments=("Wrote compile artifacts to",),
            expected_written_files=(
                "target/manifest.json",
                "target/streambuild_dag.json",
                "target/compiled/models/orders/orders_enriched.sql",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_compile_when_running_then_it_writes_target_artifacts(
    test_case: CliCompileArtifactsTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / "project"
    copytree(Path("tests/fixtures/basic_project"), project_dir)

    argv_paths: dict[str, Path] = {
        ".": project_dir,
        "target_out": project_dir / "target_out",
    }
    exit_code: int = main(tuple(str(argv_paths.get(arg, arg)) for arg in test_case.argv))
    captured_out: str = capsys.readouterr().out

    assert exit_code == test_case.expected_exit_code
    for fragment in test_case.expected_output_fragments:
        assert fragment in captured_out
    for relative_file in test_case.expected_written_files:
        assert (project_dir / relative_file).exists()
    manifest_dir_name: str = test_case.expected_target_dir_name
    manifest_contents: str = (project_dir / manifest_dir_name / "manifest.json").read_text(
        encoding="utf-8"
    )
    assert '"relations": {' in manifest_contents
    assert '"resolved_database": "analytics"' in manifest_contents
    assert '"engine": "ReplacingMergeTree(updated_at)"' in manifest_contents


@pytest.mark.parametrize(
    "test_case",
    [
        CliNestedAuditOptionsTestCase(
            description="preserves shared audit options authored before backfill",
            argv=(
                "audit",
                "--project-dir",
                "parent-project",
                "--host",
                "parent-host",
                "--port",
                "8124",
                "--username",
                "parent-user",
                "--password",
                "parent-secret",
                "--database",
                "parent-db",
                "--json",
                "--target",
                "parent-target",
                "--vars",
                '{"scope": "parent"}',
                "backfill",
            ),
            expected_project_dir="parent-project",
            expected_host="parent-host",
            expected_port=8124,
            expected_username="parent-user",
            expected_password="parent-secret",
            expected_database="parent-db",
            expected_json=True,
            expected_target="parent-target",
            expected_vars={"scope": "parent"},
        ),
        CliNestedAuditOptionsTestCase(
            description="accepts shared audit options authored after backfill",
            argv=(
                "audit",
                "backfill",
                "--project-dir",
                "child-project",
                "--host",
                "child-host",
                "--port",
                "9000",
                "--username",
                "child-user",
                "--password",
                "child-secret",
                "--database",
                "child-db",
                "--json",
                "--target",
                "child-target",
                "--vars",
                '{"scope": "child"}',
            ),
            expected_project_dir="child-project",
            expected_host="child-host",
            expected_port=9000,
            expected_username="child-user",
            expected_password="child-secret",
            expected_database="child-db",
            expected_json=True,
            expected_target="child-target",
            expected_vars={"scope": "child"},
        ),
        CliNestedAuditOptionsTestCase(
            description="child audit options override explicitly authored parent values",
            argv=(
                "audit",
                "--project-dir",
                "parent-project",
                "--host",
                "parent-host",
                "--port",
                "8124",
                "--username",
                "parent-user",
                "--password",
                "parent-secret",
                "--database",
                "parent-db",
                "--target",
                "parent-target",
                "--vars",
                '{"scope": "parent"}',
                "backfill",
                "--project-dir",
                "child-project",
                "--host",
                "child-host",
                "--port",
                "9000",
                "--username",
                "child-user",
                "--password",
                "child-secret",
                "--database",
                "child-db",
                "--json",
                "--target",
                "child-target",
                "--vars",
                '{"scope": "child"}',
            ),
            expected_project_dir="child-project",
            expected_host="child-host",
            expected_port=9000,
            expected_username="child-user",
            expected_password="child-secret",
            expected_database="child-db",
            expected_json=True,
            expected_target="child-target",
            expected_vars={"scope": "child"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_nested_audit_options_when_parsing_then_parent_and_child_order_is_stable(
    test_case: CliNestedAuditOptionsTestCase,
) -> None:
    args: argparse.Namespace = build_cli_parser().parse_args(list(test_case.argv))

    assert str(args.project_dir) == test_case.expected_project_dir
    assert args.host == test_case.expected_host
    assert args.port == test_case.expected_port
    assert args.username == test_case.expected_username
    assert args.password == test_case.expected_password
    assert args.database == test_case.expected_database
    assert args.json is test_case.expected_json
    assert args.target == test_case.expected_target
    assert args.vars == test_case.expected_vars
