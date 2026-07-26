"""Render one representative CLI output scenario from static fixtures."""

from scripts.cli_output_preview_support._helpers.renderers import (
    PREVIEW_RENDERER_BY_SCENARIO,
    PreviewRenderer,
)


def render_cli_output_preview(*, scenario_name: str, json_output: bool, verbose: bool) -> str:
    """Render the named preview scenario as the CLI would print it."""

    renderer: PreviewRenderer = PREVIEW_RENDERER_BY_SCENARIO[scenario_name]
    return renderer(json_output, verbose)
