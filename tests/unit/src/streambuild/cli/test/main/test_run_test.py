from dataclasses import replace
from pathlib import Path

import pytest

from streambuild.adapter.models import AdapterInvocationRecord
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.cli.test.main._run_test import run_test
from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import LoadedProject
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.cli.test.main._test_types import FailedTestInvocationTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        FailedTestInvocationTestCase(
            description="records terminal test failure when compilation fails",
            expected_command="test",
            expected_outcome="failed",
            expected_error_fragment="could not be parsed with Polyglot",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_test_compile_failure_when_running_then_terminal_failure_is_recorded(
    test_case: FailedTestInvocationTestCase,
    tmp_path: Path,
) -> None:
    source_project: Path = Path("examples/orders_demo")
    loaded_project: LoadedProject | None = load_project_input_for_path(path=source_project)
    profile: CompilerAdapterProfile = replace(
        build_compiler_adapter_profile(ClickHouseAdapter()),
        sql_analysis_dialect="not-a-real-dialect",
    )
    connection: RecordingAdapterConnection = RecordingAdapterConnection()

    with pytest.raises(PipelineCompileError, match=test_case.expected_error_fragment):
        run_test(
            pipelines_root=source_project / "pipelines",
            project_dir=tmp_path,
            selectors=(),
            paths=(),
            verbose=False,
            client=connection,
            loaded_project=loaded_project,
            adapter_profile=profile,
            database="analytics",
        )

    invocation: AdapterInvocationRecord = connection.invocation_observations[0]
    assert invocation.command == test_case.expected_command
    assert invocation.outcome == test_case.expected_outcome
    assert test_case.expected_error_fragment in str(invocation.error_message)
