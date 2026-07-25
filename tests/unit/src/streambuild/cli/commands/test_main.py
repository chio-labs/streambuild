from __future__ import annotations

from pathlib import Path
from shutil import copytree
from typing import cast

import pytest
from clickhouse_connect.driver.exceptions import DatabaseError

from streambuild.cli.commands.main.entry.helpers.entrypoint import resolve_clickhouse_connection
from streambuild.cli.commands.main.entry.main import _main_with_dependencies, main
from streambuild.cli.commands.main.entry.models import (
    CliEntrypointHandlers,
    ResolvedClickHouseConnection,
)
from streambuild.integrations.clickhouse.client import ClickHouseClient
from tests.unit.src.streambuild.cli.commands._test_types import (
    CliAuditBackfillProjectContextTestCase,
    CliCompileArtifactsTestCase,
    CliJanitorApplyFlagTestCase,
    CliMainEnvResolutionTestCase,
    CliMainErrorTestCase,
    CliMainIntegrationTestCase,
    CliMainJsonFlagTestCase,
    CliMainTestCase,
    CliProjectConnectionResolutionTestCase,
    CliProjectDefaultsTestCase,
    CliReconcileForwardingTestCase,
    CliSelectorForwardingTestCase,
)
from tests.unit.src.streambuild.cli.commands.helpers import (
    FakeCliClickHouseClient,
    handlers_with_overrides,
    normalize_json_output,
)


class PrintingCommandRunner:
    def __init__(self, output: str) -> None:
        self.output: str = output

    def __call__(self, *_args: object, **_kwargs: object) -> int:
        print(self.output)
        return 0


class RecordingCommandRunner:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def __call__(self, *_args: object, **kwargs: object) -> int:
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


TEST_CASES: list[CliMainTestCase] = [
    CliMainTestCase(
        description="prints discovered pipeline names as json",
        argv=("stb", "discover", "--project-dir", "tests/fixtures/basic_project"),
        expected_exit_code=0,
        expected_output_fragments=("orders",),
    ),
    CliMainTestCase(
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
    ),
    CliMainTestCase(
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
    ),
    CliMainTestCase(
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
    ),
    CliMainTestCase(
        description="prints publish payload as json",
        argv=(
            "stb",
            "publish",
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
    ),
    CliMainTestCase(
        description="prints doctor payload as json",
        argv=(
            "stb",
            "doctor",
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
    ),
    CliMainTestCase(
        description="prints repair active-view payload as json",
        argv=(
            "stb",
            "repair",
            "active-view",
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
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_cli_args_when_running_main_then_it_prints_expected_json(
    test_case: CliMainTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    handlers: CliEntrypointHandlers = handlers_with_overrides()
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())
    if test_case.argv[1] == "backfill":
        handlers = handlers_with_overrides(
            run_backfill=PrintingCommandRunner(
                "{\n"
                '  "deployment_id": "20260410T000000Z_ab12cd",\n'
                '  "boundary_time": "2026-04-10 00:00:00.000",\n'
                '  "root_reports": [{"name": "tbl__orders_enriched", '
                '"replay_strategy": "create_from_scratch"}]\n'
                "}"
            )
        )
    if test_case.argv[1:3] == ("audit", "backfill"):
        handlers = handlers_with_overrides(
            run_audit_backfill=PrintingCommandRunner(
                "{\n"
                '  "deployment_id": "20260410T000000Z_ab12cd",\n'
                '  "deployment_status": "backfilling",\n'
                '  "assessment": "ready",\n'
                '  "warning_codes": [],\n'
                '  "root_results": [{"name": "tbl__orders_enriched"}]\n'
                "}"
            )
        )
    if test_case.argv[1] == "audit" and test_case.argv[1:3] != ("audit", "backfill"):
        handlers = handlers_with_overrides(
            run_audit=PrintingCommandRunner(
                "{\n"
                '  "error_failure_count": 0,\n'
                '  "warning_failure_count": 1,\n'
                '  "audit_results": [{"severity": "warning"}]\n'
                "}"
            )
        )
    if test_case.argv[1] == "publish":
        handlers = handlers_with_overrides(
            run_publish=PrintingCommandRunner(
                "{\n"
                '  "deployment_id": "20260410T000000Z_ab12cd",\n'
                '  "published_views": [{"view_name": "tbl__orders_enriched", '
                '"target_table_name": "tbl__orders_enriched__20260410T000000Z_ab12cd"}]\n'
                "}"
            )
        )
    if test_case.argv[1] == "doctor":
        handlers = handlers_with_overrides(
            run_doctor=PrintingCommandRunner(
                "{\n"
                '  "active_views": [{"table_name": "tbl__orders_enriched", '
                '"state_kind": "logical_view_missing"}]\n'
                "}"
            )
        )
    if test_case.argv[1:3] == ("repair", "active-view"):
        handlers = handlers_with_overrides(
            run_repair_active_view=PrintingCommandRunner(
                "{\n"
                '  "table_name": "tbl__orders_enriched",\n'
                '  "target_table_name": "tbl__orders_enriched__20260410T000000Z_ab12cd"\n'
                "}"
            )
        )

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
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
    ids=["resolves project context for audit backfill"],
)
def test_given_audit_backfill_cli_args_when_running_main_then_it_forwards_project_context(
    test_case: CliAuditBackfillProjectContextTestCase,
) -> None:
    command_runner: RecordingAuditBackfillCommandRunner = RecordingAuditBackfillCommandRunner()

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        handlers=handlers_with_overrides(run_audit_backfill=command_runner),
        clickhouse_client=cast(ClickHouseClient, FakeCliClickHouseClient()),
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
    ids=["prints a clear transform sql contract error to stderr"],
)
def test_given_invalid_transform_sql_when_running_compile_then_it_prints_a_clear_error(
    test_case: CliMainErrorTestCase,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    pipeline_root: Path = tmp_path / "pipelines"
    broken_pipeline_root: Path = pipeline_root / "broken"
    broken_pipeline_root.mkdir(parents=True)
    (broken_pipeline_root / "pipeline.yml").write_text(
        """
source:
  kind: kafka
  name: orders
  broker_list: kafka:9092
  topic: source.orders
        """.strip(),
        encoding="utf-8",
    )
    (broken_pipeline_root / "orders_enriched.sql").write_text(
        """
MODEL (
  engine: "MergeTree()",
  order_by: ["order_id"],
);

SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
UNION ALL
SELECT CAST(order_id AS UInt64) AS order_id FROM replay_orders
        """.strip(),
        encoding="utf-8",
    )
    argv: list[str] = [
        str(pipeline_root) if part == "BROKEN_PIPELINES_ROOT" else part for part in test_case.argv
    ]

    exit_code: int = main(argv)
    captured_error: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    for expected_fragment in test_case.expected_error_fragments:
        assert expected_fragment in captured_error


PLAN_OUTPUT_TEST_CASES: list[CliMainIntegrationTestCase] = [
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
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLAN_OUTPUT_TEST_CASES,
    ids=[case.description for case in PLAN_OUTPUT_TEST_CASES],
)
def test_given_cli_args_when_running_plan_then_it_prints_expected_output(
    test_case: CliMainIntegrationTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_plan=PlanCommandRunner())
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
    )
    captured_output: str = capsys.readouterr().out
    normalized_output: str = (
        normalize_json_output(captured_output) if "--json" in test_case.argv else captured_output
    )

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
                "database": None,
                "selectors": (),
                "full_refresh": False,
                "start_time": None,
                "json_output": False,
                "verbose": False,
            },
        )
    ],
    ids=["uses clickhouse env vars for plan defaults"],
)
def test_given_clickhouse_env_vars_when_running_plan_then_it_uses_env_defaults(
    test_case: CliMainEnvResolutionTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_plan=runner)
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        environment=test_case.env_vars,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
    )

    assert exit_code == test_case.expected_exit_code
    assert runner.kwargs == {**test_case.expected_kwargs, "client": clickhouse_client}


@pytest.mark.parametrize(
    "test_case",
    [
        CliProjectDefaultsTestCase(
            description="uses project yaml database default for plan",
            command_name="plan",
            expected_database="analytics",
        )
    ],
    ids=["uses project yaml database default for plan"],
)
def test_given_project_yaml_when_running_plan_then_it_uses_project_database_defaults(
    test_case: CliProjectDefaultsTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root: Path = tmp_path / "demo"
    pipelines_root: Path = project_root / "pipelines"
    orders_root: Path = pipelines_root / "orders"
    orders_root.mkdir(parents=True)
    (project_root / "streambuild_project.yml").write_text(
        """
default_database: analytics

clickhouse:
  host: localhost
  port: 8123
  username: streambuild
  password: streambuild
        """.strip(),
        encoding="utf-8",
    )
    (orders_root / "pipeline.yml").write_text(
        """
source:
  kind: kafka
  name: orders
  broker_list: kafka:9092
  topic: source.orders
        """.strip(),
        encoding="utf-8",
    )
    (orders_root / "orders_enriched.sql").write_text(
        """
MODEL (
  engine: "MergeTree()",
  order_by: ["order_id"],
);

SELECT order_id::UInt64 AS order_id FROM __ref("orders")
        """.strip(),
        encoding="utf-8",
    )

    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_plan=runner)
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())
    monkeypatch.chdir(project_root)

    exit_code: int = _main_with_dependencies(
        ("stb", "plan"),
        handlers=handlers,
        clickhouse_client=clickhouse_client,
    )

    assert exit_code == 0
    assert runner.kwargs == {
        "database": test_case.expected_database,
        "selectors": (),
        "full_refresh": False,
        "start_time": None,
        "json_output": False,
        "verbose": False,
        "client": clickhouse_client,
    }


RUNTIME_PROJECT_DEFAULTS_TEST_CASES: list[CliProjectDefaultsTestCase] = [
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
]

RUNTIME_PROJECT_DIR_DEFAULTS_TEST_CASES: list[CliProjectDefaultsTestCase] = [
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
]


@pytest.mark.parametrize(
    "test_case",
    RUNTIME_PROJECT_DEFAULTS_TEST_CASES,
    ids=[case.description for case in RUNTIME_PROJECT_DEFAULTS_TEST_CASES],
)
def test_given_project_yaml_when_running_runtime_command_then_it_uses_project_defaults(
    test_case: CliProjectDefaultsTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root: Path = tmp_path / "demo"
    pipelines_root: Path = project_root / "pipelines"
    orders_root: Path = pipelines_root / "orders"
    orders_root.mkdir(parents=True)
    (project_root / "streambuild_project.yml").write_text(
        """
default_database: analytics

clickhouse:
  host: localhost
  port: 8123
  username: streambuild
  password: streambuild
        """.strip(),
        encoding="utf-8",
    )
    (orders_root / "pipeline.yml").write_text(
        """
source:
  kind: kafka
  name: orders
  broker_list: kafka:9092
  topic: source.orders
        """.strip(),
        encoding="utf-8",
    )
    (orders_root / "orders_enriched.sql").write_text(
        """
MODEL (
  engine: "MergeTree()",
  order_by: ["order_id"],
);

SELECT order_id::UInt64 AS order_id FROM __ref("orders")
        """.strip(),
        encoding="utf-8",
    )

    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers
    if test_case.command_name == "audit backfill":
        handlers = handlers_with_overrides(run_audit_backfill=runner)
    elif test_case.command_name == "publish":
        handlers = handlers_with_overrides(run_publish=runner)
    else:
        handlers = handlers_with_overrides(run_doctor=runner)
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())
    monkeypatch.chdir(project_root)

    argv: tuple[str, ...]
    if test_case.command_name == "audit backfill":
        argv = ("stb", "audit", "backfill")
    elif test_case.command_name == "publish":
        argv = ("stb", "publish")
    else:
        argv = ("stb", "doctor")

    exit_code: int = _main_with_dependencies(
        argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
    )

    assert exit_code == 0
    assert runner.kwargs["database"] == test_case.expected_database
    assert runner.kwargs["client"] == clickhouse_client


@pytest.mark.parametrize(
    "test_case",
    RUNTIME_PROJECT_DIR_DEFAULTS_TEST_CASES,
    ids=[case.description for case in RUNTIME_PROJECT_DIR_DEFAULTS_TEST_CASES],
)
def test_given_project_dir_when_running_runtime_command_then_it_uses_project_defaults(
    test_case: CliProjectDefaultsTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root: Path = tmp_path / "demo"
    pipelines_root: Path = project_root / "pipelines"
    orders_root: Path = pipelines_root / "orders"
    orders_root.mkdir(parents=True)
    (project_root / "streambuild_project.yml").write_text(
        """
default_database: analytics

clickhouse:
  host: localhost
  port: 8123
  username: streambuild
  password: streambuild
        """.strip(),
        encoding="utf-8",
    )
    (orders_root / "pipeline.yml").write_text(
        """
source:
  kind: kafka
  name: orders
  broker_list: kafka:9092
  topic: source.orders
        """.strip(),
        encoding="utf-8",
    )
    (orders_root / "orders_enriched.sql").write_text(
        """
MODEL (
  engine: "MergeTree()",
  order_by: ["order_id"],
);

SELECT order_id::UInt64 AS order_id FROM __ref("orders")
        """.strip(),
        encoding="utf-8",
    )

    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers
    if test_case.command_name == "audit backfill":
        handlers = handlers_with_overrides(run_audit_backfill=runner)
    elif test_case.command_name == "publish":
        handlers = handlers_with_overrides(run_publish=runner)
    else:
        handlers = handlers_with_overrides(run_doctor=runner)
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())
    monkeypatch.chdir(tmp_path)

    argv: tuple[str, ...]
    if test_case.command_name == "audit backfill":
        argv = ("stb", "audit", "backfill", "--project-dir", str(project_root))
    elif test_case.command_name == "publish":
        argv = ("stb", "publish", "--project-dir", str(project_root))
    else:
        argv = ("stb", "doctor", "--project-dir", str(project_root))

    exit_code: int = _main_with_dependencies(
        argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
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
    ids=["uses project clickhouse defaults when cli and env are absent"],
)
def test_given_project_clickhouse_defaults_when_resolving_connection_then_it_uses_them(
    test_case: CliProjectConnectionResolutionTestCase,
) -> None:
    project_connection: ResolvedClickHouseConnection = ResolvedClickHouseConnection(
        host=test_case.expected_project_connection[0],
        port=test_case.expected_project_connection[1],
        username=test_case.expected_project_connection[2],
        password=test_case.expected_project_connection[3],
    )

    resolved_connection: ResolvedClickHouseConnection = resolve_clickhouse_connection(
        host=None,
        port=None,
        username=None,
        password=None,
        project_connection=project_connection,
    )

    assert resolved_connection == ResolvedClickHouseConnection(
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
    ids=["passes json flag through to plan command"],
)
def test_given_json_flag_when_running_plan_then_it_passes_json_output_to_command(
    test_case: CliMainJsonFlagTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_plan=runner)
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
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
    ids=["passes selectors and full refresh through to plan command"],
)
def test_given_selectors_when_running_plan_then_it_passes_selection_kwargs_to_command(
    test_case: CliSelectorForwardingTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_plan=runner)
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
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
    ids=["passes apply flag through to janitor command"],
)
def test_given_apply_flag_when_running_janitor_then_it_passes_apply_to_command(
    test_case: CliJanitorApplyFlagTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_janitor=runner)
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
    )

    assert exit_code == test_case.expected_exit_code
    assert runner.kwargs["apply"] is test_case.expected_apply
    assert "metadata_database" not in runner.kwargs


CLI_EXPECTED_ERROR_TEST_CASES: list[CliMainErrorTestCase] = [
    CliMainErrorTestCase(
        description="prints command value errors without a traceback",
        argv=(
            "stb",
            "publish",
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
]


@pytest.mark.parametrize(
    "test_case",
    CLI_EXPECTED_ERROR_TEST_CASES,
    ids=[case.description for case in CLI_EXPECTED_ERROR_TEST_CASES],
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
            DatabaseError(
                "Code: 516. DB::Exception: Authentication failed. (AUTHENTICATION_FAILED)"
            )
        ),
    )
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
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
    ids=["passes json flag through to backfill command"],
)
def test_given_json_flag_when_running_backfill_then_it_passes_json_output_to_command(
    test_case: CliMainJsonFlagTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_backfill=runner)
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
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
    ids=["passes selectors and full refresh through to backfill command"],
)
def test_given_selectors_when_running_backfill_then_it_passes_selection_kwargs_to_command(
    test_case: CliSelectorForwardingTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_backfill=runner)
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
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
    ids=["passes selectors, apply, and json flags through to reconcile command"],
)
def test_given_reconcile_flags_when_running_reconcile_then_it_passes_kwargs_to_command(
    test_case: CliReconcileForwardingTestCase,
) -> None:
    runner: RecordingCommandRunner = RecordingCommandRunner()
    handlers: CliEntrypointHandlers = handlers_with_overrides(run_reconcile=runner)
    clickhouse_client: ClickHouseClient = cast(ClickHouseClient, FakeCliClickHouseClient())

    exit_code: int = _main_with_dependencies(
        test_case.argv,
        handlers=handlers,
        clickhouse_client=clickhouse_client,
    )

    assert exit_code == test_case.expected_exit_code
    assert runner.kwargs["selectors"] == test_case.expected_selectors
    assert runner.kwargs["apply"] is test_case.expected_apply
    assert runner.kwargs["json_output"] is test_case.expected_json_output


COMPILE_ARTIFACT_TEST_CASES: list[CliCompileArtifactsTestCase] = [
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
            "target_out/orders/compile/models/orders_enriched.sql",
            "target_out/orders/run/models/orders_enriched.table.sql",
            "target_out/orders/run/models/orders_enriched.mv.sql",
            "target_out/orders/run/workflow/01_kafka_table.sql",
            "target_out/orders/run/workflow/02_raw_table.sql",
            "target_out/orders/run/workflow/03_landing_mv.sql",
            "target_out/orders/run/workflow/10_orders_enriched.table.sql",
            "target_out/orders/run/workflow/11_orders_enriched.mv.sql",
            "target_out/orders/run/workflow/workflow.sql",
            "target_out/orders/run/workflow/workflow.json",
        ),
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
            "target/orders/compile/models/orders_enriched.sql",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    COMPILE_ARTIFACT_TEST_CASES,
    ids=[case.description for case in COMPILE_ARTIFACT_TEST_CASES],
)
def test_given_compile_when_running_then_it_writes_target_artifacts(
    test_case: CliCompileArtifactsTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / "project"
    copytree(Path("tests/fixtures/basic_project"), project_dir)

    exit_code: int = main(
        tuple(
            str(
                project_dir
                if arg == "."
                else (project_dir / "target_out" if arg == "target_out" else arg)
            )
            for arg in test_case.argv
        )
    )
    captured_out: str = capsys.readouterr().out

    assert exit_code == test_case.expected_exit_code
    for fragment in test_case.expected_output_fragments:
        assert fragment in captured_out
    for relative_file in test_case.expected_written_files:
        assert (project_dir / relative_file).exists()
    manifest_dir_name: str = "target_out" if "target_out" in test_case.argv else "target"
    manifest_contents: str = (project_dir / manifest_dir_name / "manifest.json").read_text(
        encoding="utf-8"
    )
    assert '"relations": {' in manifest_contents
    assert '"resolved_database": "default"' in manifest_contents
    assert '"engine": "ReplacingMergeTree(updated_at)"' in manifest_contents
