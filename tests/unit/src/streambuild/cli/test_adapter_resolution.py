from __future__ import annotations

from pathlib import Path
from shutil import copytree

import pytest

from streambuild.adapter.models import AdapterConnectionConfig
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry.main.main import _main_with_dependencies
from streambuild.cli.entry.models import CliConnectionOptions, CliEntrypointHandlers
from tests.unit.src.streambuild.cli._test_types import (
    CliAdapterPlanExecutionTestCase,
    CliAdapterRejectionTestCase,
    CliCredentialRedactionTestCase,
)
from tests.unit.src.streambuild.cli.helpers import (
    AdapterConnectionProvider,
    RecordingAdapterConnection,
    handlers_with_overrides,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CliAdapterRejectionTestCase(
            description="rejects an unknown adapter before resolving credentials or connecting",
            project_file_contents="version: 2\nadapter: duckdb\ndefault_database: analytics\n",
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
    (project_dir / "streambuild_project.yml").write_text(
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
version: 2
adapter: clickhouse
default_database: analytics
clickhouse:
  host: project-host
  port: 8123
  username: project-user
  password: project-secret
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
    (project_dir / "streambuild_project.yml").write_text(
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
