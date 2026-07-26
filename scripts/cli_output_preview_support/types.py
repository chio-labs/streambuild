"""Preview support types."""

from collections.abc import Callable

from scripts.cli_output_preview_support.models import PreviewRequest

type PreviewRenderer = Callable[[PreviewRequest], str]
