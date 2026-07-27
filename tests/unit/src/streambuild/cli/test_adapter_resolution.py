from __future__ import annotations

import re
from pathlib import Path
from shutil import copytree
from unittest.mock import Mock

import pytest

from streambuild.adapter.models import AdapterConnectionConfig
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry.main.main import _main_with_dependencies
from streambuild.cli.entry.models import CliConnectionOptions, CliEntrypointHandlers
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import LoadedProject
from tests.unit.src.streambuild.cli._test_types import (
    CliAdapterPlanExecutionTestCase,
    CliAdapterRejectionTestCase,
    CliCredentialRedactionTestCase,
    CliLazyConnectionTestCase,
    CliProjectSecretRedactionTestCase,
    CliTargetSelectionTestCase,
)
from tests.unit.src.streambuild.cli.helpers import (
    AdapterConnectionProvider,
    RecordingAdapterConnection,
    handlers_with_overrides,
    write_cli_compilation_project,
    write_cli_target_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CliAdapterRejectionTestCase(
            description="rejects an unknown adapter before resolving credentials or connecting",
            project_file_contents=(
                'name = "selector_project"\nadapter = "duckdb"\n'
                'default_target = "test"\n[targets.test]\ndatabase = "analytics"\n'
            ),
            argv=("stb", "plan"),
            expected_exit_code=1,
            expected_error_fragments=(
                "Unsupported adapter 'duckdb'",
                "Supported adapters: clickhouse.",
            ),
            expected_absent_error_fragments=("Missing host", "Traceback"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_project_adapter_when_running_plan_then_it_fails_before_connecting(
    test_case: CliAdapterRejectionTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / "project"
    copytree(Path("tests/fixtures/selector_project"), project_dir)
    (project_dir / "streambuild_project.toml").write_text(
        test_case.project_file_contents, encoding="utf-8"
    )
    handlers: CliEntrypointHandlers = handlers_with_overrides()

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        environment={},
        working_directory=project_dir,
    )
    captured_error: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    expected_fragment: str
    for expected_fragment in test_case.expected_error_fragments:
        assert expected_fragment in captured_error
    absent_fragment: str
    for absent_fragment in test_case.expected_absent_error_fragments:
        assert absent_fragment not in captured_error


@pytest.mark.parametrize(
    "test_case",
    [
        CliAdapterPlanExecutionTestCase(
            description=("runs plan through the resolved adapter with mixed connection precedence"),
            project_file_contents="""
name = "selector_project"
adapter = "clickhouse"
default_target = "test"

[settings]
virtual_environments = true

[connection]
host = "project-host"
port = 8123
username = "project-user"
password = "project-secret"

[targets.test]
database = "analytics"
""".lstrip(),
            argv=("stb", "plan", "--host", "cli-host"),
            environment={
                "STREAMBUILD_CLICKHOUSE_PORT": "9000",
                "STREAMBUILD_CLICKHOUSE_USERNAME": "env-user",
            },
            expected_exit_code=0,
            expected_connection=("cli-host", 9000, "env-user", "project-secret"),
            expected_catalog_load_count=1,
            expected_query_count=1,
            expected_connection_closed=True,
            expected_stdout="""Plan Ready
Database: analytics
Subtrees to rebuild: 2
Planned steps: 12

Subtrees:
Subtree 1
[replay start] raw__orders
\u251c\u2500\u2500 [live target] tbl__orders_clean
\u2514\u2500\u2500 [live target] tbl__orders_enriched

Subtree 2
[replay start] raw__payments
\u2514\u2500\u2500 [live target] tbl__payments_enriched

New targets:
- tbl__orders_clean
- tbl__orders_enriched
- tbl__payments_enriched

Diffs:
- kafka__orders
- kafka__payments
- mv__orders
- tbl__orders_clean
- tbl__orders_enriched
- mv__payments
- tbl__payments_enriched
- raw__orders
- raw__payments
Run `stb plan --verbose` to show full diffs

Warnings:
- none
""",
            expected_redacted_secret="project-secret",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_versioned_project_when_running_plan_then_adapter_preserves_exact_output_and_closes(
    test_case: CliAdapterPlanExecutionTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "project"
    copytree(Path("tests/fixtures/selector_project"), project_dir)
    (project_dir / "streambuild_project.toml").write_text(
        test_case.project_file_contents, encoding="utf-8"
    )
    connection: RecordingAdapterConnection = RecordingAdapterConnection()
    provider: AdapterConnectionProvider = AdapterConnectionProvider(connection)
    monkeypatch.setattr(ClickHouseAdapter, "connect", provider)
    handlers: CliEntrypointHandlers = handlers_with_overrides()

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=handlers,
        environment=test_case.environment,
        working_directory=project_dir,
    )
    captured_stdout: str = capsys.readouterr().out

    assert exit_code == test_case.expected_exit_code
    assert provider.config is not None
    assert (
        provider.config.host,
        provider.config.port,
        provider.config.username,
        provider.config.password,
    ) == test_case.expected_connection
    assert len(connection.catalog_databases) == test_case.expected_catalog_load_count
    assert len(connection.statements) == test_case.expected_query_count
    assert connection.closed is test_case.expected_connection_closed
    assert captured_stdout == test_case.expected_stdout
    assert test_case.expected_redacted_secret not in repr(provider.config)


@pytest.mark.parametrize(
    "test_case",
    [
        CliCredentialRedactionTestCase(
            description="does not expose resolved CLI credentials through repr",
            password="cli-secret",
            expected_absent_fragment="cli-secret",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cli_connection_options_when_rendering_then_credentials_are_not_exposed(
    test_case: CliCredentialRedactionTestCase,
) -> None:
    options: CliConnectionOptions = CliConnectionOptions(
        host="localhost",
        port=8123,
        username="streambuild",
        password=test_case.password,
        project_connection=AdapterConnectionConfig(
            host="localhost",
            port=8123,
            username="streambuild",
            password=test_case.password,
        ),
    )

    assert test_case.expected_absent_fragment not in repr(options)


@pytest.mark.parametrize(
    "test_case",
    [
        CliLazyConnectionTestCase(
            description="offline compile defers a missing password but plan rejects it before IO",
            project_vars_contents="",
            secret_template="${ENV:OFFLINE_PASSWORD}",
            expected_compile_exit_code=0,
            expected_plan_exit_code=1,
            expected_connect_count=0,
            expected_error_fragment="connection.password references missing environment variable",
            expected_absent_fragment="LOWER_PRIORITY_PASSWORD",
        ),
        CliLazyConnectionTestCase(
            description="offline compile defers a variable-indirected missing password",
            project_vars_contents=('[vars]\nwarehouse_password = "${ENV:OFFLINE_PASSWORD}"\n\n'),
            secret_template="${warehouse_password}",
            expected_compile_exit_code=0,
            expected_plan_exit_code=1,
            expected_connect_count=0,
            expected_error_fragment=(
                "connection.password vars.warehouse_password references missing "
                "environment variable"
            ),
            expected_absent_fragment="LOWER_PRIORITY_PASSWORD",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_lazy_connection_secret_when_compiling_then_only_connecting_command_expands_it(
    test_case: CliLazyConnectionTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "project"
    target_dir: Path = tmp_path / "artifacts"
    copytree(Path("tests/fixtures/selector_project"), project_dir)
    (project_dir / "streambuild_project.toml").write_text(
        'name = "selector_project"\ndefault_target = "test"\n\n'
        "[settings]\nvirtual_environments = true\n\n"
        f"{test_case.project_vars_contents}"
        '[connection]\npassword = "${ENV:LOWER_PRIORITY_PASSWORD}"\n\n'
        '[targets.test]\ndatabase = "analytics"\n\n'
        '[targets.test.connection]\nhost = "localhost"\nport = 8123\n'
        f'username = "streambuild"\npassword = "{test_case.secret_template}"\n',
        encoding="utf-8",
    )
    connect: Mock = Mock(side_effect=AssertionError("connection IO occurred"))
    monkeypatch.setattr(ClickHouseAdapter, "connect", connect)
    handlers: CliEntrypointHandlers = handlers_with_overrides()

    compile_exit_code: int = _main_with_dependencies(
        argv=("stb", "compile", "--target-dir", str(target_dir)),
        handlers=handlers,
        environment={},
        working_directory=project_dir,
    )
    compile_output: str = capsys.readouterr().out
    plan_exit_code: int = _main_with_dependencies(
        argv=("stb", "plan"),
        handlers=handlers,
        environment={},
        working_directory=project_dir,
    )
    plan_error: str = capsys.readouterr().err
    artifact_contents: tuple[str, ...] = tuple(
        path.read_text(encoding="utf-8") for path in sorted(target_dir.rglob("*.*"))
    )

    assert compile_exit_code == test_case.expected_compile_exit_code
    assert plan_exit_code == test_case.expected_plan_exit_code
    assert connect.call_count == test_case.expected_connect_count
    assert test_case.expected_error_fragment in plan_error
    assert test_case.expected_absent_fragment not in compile_output
    assert test_case.expected_absent_fragment not in plan_error
    assert all(test_case.expected_absent_fragment not in contents for contents in artifact_contents)


@pytest.mark.parametrize(
    "test_case",
    [
        CliProjectSecretRedactionTestCase(
            description="redacts a resolved project secret from repr errors and compile artifacts",
            secret="resolved-project-secret",
            expected_compile_exit_code=0,
            expected_plan_exit_code=1,
            expected_error_fragment="streambuild_project.toml.*connection.*warehouse",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_resolved_project_secret_when_rendering_surfaces_then_it_is_never_exposed(
    test_case: CliProjectSecretRedactionTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "project"
    target_dir: Path = tmp_path / "artifacts"
    write_cli_compilation_project(
        project_root=project_dir,
        model_sql="""
        MODEL (order_by: ["order_id"]);
        SELECT order_id::UInt64 AS order_id FROM __source("orders")
        """,
    )
    (project_dir / "streambuild_project.toml").write_text(
        'name = "redaction_project"\ndefault_target = "test"\n\n'
        "[settings]\nvirtual_environments = true\n\n"
        f'[vars]\nwarehouse_password = "{test_case.secret}"\n\n'
        '[connection]\nhost = "localhost"\nport = 8123\n'
        'username = "streambuild"\npassword = "${warehouse_password}"\nwarehouse = "bad"\n\n'
        '[targets.test]\ndatabase = "analytics"\n',
        encoding="utf-8",
    )
    loaded_project: LoadedProject | None = load_project_input_for_path(path=project_dir)
    connect: Mock = Mock(side_effect=AssertionError("connection IO occurred"))
    monkeypatch.setattr(ClickHouseAdapter, "connect", connect)
    handlers: CliEntrypointHandlers = handlers_with_overrides()

    compile_exit_code: int = _main_with_dependencies(
        argv=("stb", "compile", "--target-dir", str(target_dir)),
        handlers=handlers,
        environment={},
        working_directory=project_dir,
    )
    compile_output: str = capsys.readouterr().out
    plan_exit_code: int = _main_with_dependencies(
        argv=("stb", "plan"),
        handlers=handlers,
        environment={},
        working_directory=project_dir,
    )
    plan_error: str = capsys.readouterr().err
    artifact_contents: tuple[str, ...] = tuple(
        path.read_text(encoding="utf-8") for path in sorted(target_dir.rglob("*.*"))
    )
    assert loaded_project is not None
    rendered_debug_values: tuple[str, ...] = (
        repr(loaded_project),
        repr(loaded_project.configuration),
        repr(loaded_project.effective_configuration),
    )

    assert compile_exit_code == test_case.expected_compile_exit_code
    assert plan_exit_code == test_case.expected_plan_exit_code
    assert connect.call_count == 0
    assert re.search(test_case.expected_error_fragment, plan_error) is not None
    assert test_case.secret not in compile_output
    assert test_case.secret not in plan_error
    assert all(test_case.secret not in contents for contents in artifact_contents)
    assert all(test_case.secret not in rendered for rendered in rendered_debug_values)


@pytest.mark.parametrize(
    "test_case",
    [
        CliTargetSelectionTestCase(
            description="nested compile uses the project default target",
            argv_suffix=(),
            local_contents="",
            expected_database_fragment='"resolved_database": "dev_database"',
        ),
        CliTargetSelectionTestCase(
            description="nested compile uses a local target and local variable",
            argv_suffix=(),
            local_contents="""
            target = "private"
            [targets.private.vars]
            database_name = "local_database"
            """,
            expected_database_fragment='"resolved_database": "local_database"',
        ),
        CliTargetSelectionTestCase(
            description="CLI target and vars override local and project selection",
            argv_suffix=(
                "--target",
                "private",
                "--vars",
                '{"database_name": "cli_database"}',
            ),
            local_contents="""
            target = "dev"
            [vars]
            database_name = "local_database"
            """,
            expected_database_fragment='"resolved_database": "cli_database"',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_inputs_when_nested_compile_then_precedence_applies(
    test_case: CliTargetSelectionTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    target_dir: Path = tmp_path / "target"
    write_cli_target_project(
        project_root=project_dir,
        local_contents=test_case.local_contents,
    )

    exit_code: int = _main_with_dependencies(
        argv=("stb", "compile", "--target-dir", str(target_dir), *test_case.argv_suffix),
        handlers=handlers_with_overrides(),
        environment={},
        working_directory=project_dir / "pipelines" / "orders",
    )
    manifest: str = (target_dir / "manifest.json").read_text(encoding="utf-8")

    assert exit_code == 0
    assert test_case.expected_database_fragment in manifest
