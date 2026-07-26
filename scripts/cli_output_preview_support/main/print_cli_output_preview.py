"""Print one or every representative CLI output scenario."""

from scripts.cli_output_preview_support.constants import (
    ALL_SCENARIOS_CHOICE,
    PREVIEW_DATABASE,
    PREVIEW_RENDERER_BY_SCENARIO,
    PREVIEW_SCENARIO_NAMES,
)
from scripts.cli_output_preview_support.models import PreviewRequest
from scripts.cli_output_preview_support.types import PreviewRenderer


def print_cli_output_preview(*, scenario: str, json_output: bool, verbose: bool) -> int:
    """Print the requested preview scenarios and return a process exit code."""

    requested: tuple[str, ...] = (
        PREVIEW_SCENARIO_NAMES if scenario == ALL_SCENARIOS_CHOICE else (scenario,)
    )
    request: PreviewRequest = PreviewRequest(
        database=PREVIEW_DATABASE,
        json_output=json_output,
        verbose=verbose,
    )
    scenario_name: str
    for index, scenario_name in enumerate(requested):
        if index > 0:
            print("\n---\n")
        renderer: PreviewRenderer = PREVIEW_RENDERER_BY_SCENARIO[scenario_name]
        print(renderer(request))
    return 0
