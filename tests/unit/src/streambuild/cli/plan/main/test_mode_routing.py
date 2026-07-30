import json
from pathlib import Path

import pytest

from streambuild.cli.plan.constants import DIRECT_MODE_LABEL, VIRTUAL_ENVIRONMENTS_MODE_LABEL
from tests.unit.src.streambuild.cli.plan.main._test_types import (
    CliDirectPlanFlagRejectionTestCase,
    CliPlanModeRoutingTestCase,
)
from tests.unit.src.streambuild.cli.plan.main.helpers import run_scope_project_plan
from tests.unit.src.streambuild.compiler.planner.helpers import write_direct_scope_project


@pytest.mark.parametrize(
    "test_case",
    [
        CliPlanModeRoutingTestCase(
            description="an omitted virtual_environments setting plans in direct mode",
            virtual_environments=None,
            expected_mode=DIRECT_MODE_LABEL,
            expected_title="Direct Plan",
        ),
        CliPlanModeRoutingTestCase(
            description="a disabled virtual_environments setting plans in direct mode",
            virtual_environments=False,
            expected_mode=DIRECT_MODE_LABEL,
            expected_title="Direct Plan",
        ),
        CliPlanModeRoutingTestCase(
            description="an enabled virtual_environments setting preserves deployment planning",
            virtual_environments=True,
            expected_mode=VIRTUAL_ENVIRONMENTS_MODE_LABEL,
            expected_title="Plan Ready",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_effective_project_mode_when_planning_then_that_mode_is_used(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], test_case: CliPlanModeRoutingTestCase
) -> None:
    write_direct_scope_project(
        project_root=tmp_path, virtual_environments=test_case.virtual_environments
    )

    text_exit_code: int = run_scope_project_plan(project_root=tmp_path, json_output=False)
    text_output: str = capsys.readouterr().out
    json_exit_code: int = run_scope_project_plan(project_root=tmp_path, json_output=True)
    payload: dict[str, object] = json.loads(capsys.readouterr().out)

    assert (text_exit_code, json_exit_code) == (0, 0)
    assert test_case.expected_title in text_output
    assert payload["mode"] == test_case.expected_mode
    assert payload["adapter"] == "clickhouse"


@pytest.mark.parametrize(
    "test_case",
    [
        CliPlanModeRoutingTestCase(
            description="direct mode reports the complete closure and its single replay root",
            virtual_environments=None,
            expected_mode=DIRECT_MODE_LABEL,
            expected_title="Direct Plan",
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
            expected_replay_root_models=("alpha",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_mode_when_planning_then_full_closure_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], test_case: CliPlanModeRoutingTestCase
) -> None:
    write_direct_scope_project(
        project_root=tmp_path, virtual_environments=test_case.virtual_environments
    )

    exit_code: int = run_scope_project_plan(project_root=tmp_path, json_output=True)

    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert tuple(payload["execution_scope"]) == test_case.expected_execution_scope
    assert payload["database"] == "analytics"
    assert (
        tuple(root["model"] for root in payload["replay_roots"])
        == test_case.expected_replay_root_models
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectPlanFlagRejectionTestCase(
            description="--full-refresh is rejected in direct mode",
            full_refresh=True,
            start_time=None,
            expected_error_fragment="--full-refresh is a virtual-environment replay control",
        ),
        CliDirectPlanFlagRejectionTestCase(
            description="--start-time is rejected in direct mode",
            full_refresh=False,
            start_time="2026-01-01",
            expected_error_fragment="--start-time is a virtual-environment replay control",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_replay_control_flag_in_direct_mode_when_planning_then_command_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    test_case: CliDirectPlanFlagRejectionTestCase,
) -> None:
    write_direct_scope_project(project_root=tmp_path)

    exit_code: int = run_scope_project_plan(
        project_root=tmp_path,
        json_output=False,
        selectors=("alpha",),
        full_refresh=test_case.full_refresh,
        start_time=test_case.start_time,
    )

    assert exit_code == 1
    assert test_case.expected_error_fragment in capsys.readouterr().err
