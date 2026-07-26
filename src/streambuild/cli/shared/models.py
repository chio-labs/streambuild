from __future__ import annotations

from dataclasses import dataclass

from streambuild.cli.shared.constants import ANSI_RESET
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.compiler.shared.models import ObjectKey
from streambuild.spec.types import ReplayLineageMode


@dataclass(frozen=True)
class BackfillPreviewContext:
    resolved_database: str
    resolved_metadata_database: str
    desired_state: DesiredState
    plan: DeploymentPlan
    replay_lineage_mode: ReplayLineageMode
    full_refresh_keys: frozenset[ObjectKey] = frozenset()
    start_time_keys: frozenset[ObjectKey] = frozenset()
    start_time: str | None = None


@dataclass(frozen=True)
class SelectionResolution:
    desired_state: DesiredState
    selected_model_keys: frozenset[ObjectKey]
    replay_lineage_mode: ReplayLineageMode


@dataclass(frozen=True)
class CompactChangedTargetSummary:
    target_name: str
    detail_lines: tuple[str, ...]


@dataclass(frozen=True)
class TextStyle:
    """One ANSI style role in the CLI theme."""

    prefix: str
    suffix: str = ANSI_RESET

    def apply(self, *, text: str, use_color: bool) -> str:
        """Apply this style when color is enabled and there is text to style."""

        if not use_color or not self.prefix or not text:
            return text
        return f"{self.prefix}{text}{self.suffix}"


@dataclass(frozen=True)
class CliTheme:
    """Semantic style roles for human CLI output."""

    title: TextStyle
    section: TextStyle
    subsection: TextStyle
    label: TextStyle
    object_name: TextStyle
    warning: TextStyle
    ready: TextStyle
    not_ready: TextStyle
    caution: TextStyle
    diff_context: TextStyle
    diff_added: TextStyle
    diff_removed: TextStyle
    muted: TextStyle
    muted_strong: TextStyle
    passed: TextStyle
    failed: TextStyle
    passed_strong: TextStyle
    failed_strong: TextStyle
