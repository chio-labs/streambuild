"""Semantic styling class for human CLI output."""

from __future__ import annotations

from streambuild.cli.shared.constants import (
    ANSI_BLUE,
    ANSI_BOLD,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_RED,
    ANSI_YELLOW,
)
from streambuild.cli.shared.models import CliTheme, TextStyle
from streambuild.executor.audit_backfill.types import AuditAssessment

default_cli_theme: CliTheme = CliTheme(
    title=TextStyle(ANSI_BOLD + ANSI_BLUE),
    section=TextStyle(ANSI_BOLD + ANSI_BLUE),
    subsection=TextStyle(ANSI_BOLD),
    label=TextStyle(ANSI_DIM),
    object_name=TextStyle(ANSI_BOLD),
    warning=TextStyle(ANSI_YELLOW),
    ready=TextStyle(ANSI_GREEN),
    not_ready=TextStyle(ANSI_RED),
    caution=TextStyle(ANSI_YELLOW),
    diff_context=TextStyle(ANSI_DIM),
    diff_added=TextStyle(ANSI_GREEN),
    diff_removed=TextStyle(ANSI_RED),
    muted=TextStyle(ANSI_DIM),
    muted_strong=TextStyle(ANSI_DIM + ANSI_BOLD),
    passed=TextStyle(ANSI_GREEN),
    failed=TextStyle(ANSI_RED),
    passed_strong=TextStyle(ANSI_GREEN + ANSI_BOLD),
    failed_strong=TextStyle(ANSI_RED + ANSI_BOLD),
)

_DIFF_CONTEXT_PREFIXES: tuple[str, ...] = ("+++", "---", "@@")
_DIFF_ADDED_PREFIX: str = "+"
_DIFF_REMOVED_PREFIX: str = "-"


class CliStyle:
    """Semantic CLI styling facade used by human-output formatters."""

    def __init__(self, *, use_color: bool, theme: CliTheme = default_cli_theme) -> None:
        self.use_color: bool = use_color
        self.theme: CliTheme = theme

    def title(self, text: str) -> str:
        """Style a top-level title."""

        return self.theme.title.apply(text=text, use_color=self.use_color)

    def section(self, text: str) -> str:
        """Style a section heading, which carries its own colon."""

        return self.theme.section.apply(text=f"{text}:", use_color=self.use_color)

    def subsection(self, text: str) -> str:
        """Style a subsection heading."""

        return self.theme.subsection.apply(text=text, use_color=self.use_color)

    def label(self, text: str) -> str:
        """Style a field label."""

        return self.theme.label.apply(text=text, use_color=self.use_color)

    def label_value(self, *, label: str, value: str) -> str:
        """Render a styled label beside its unstyled value."""

        return f"{self.label(label)}: {value}"

    def object_name(self, *, text: str, assessment: AuditAssessment | None = None) -> str:
        """Style a warehouse object name, optionally coloured by assessment."""

        if assessment is None:
            return self.theme.object_name.apply(text=text, use_color=self.use_color)
        return self.assessment_value(text=text, assessment=assessment, bold=True)

    def warning(self, text: str) -> str:
        """Style warning text."""

        return self.theme.warning.apply(text=text, use_color=self.use_color)

    def assessment(self, text: str) -> str:
        """Style an assessment word using the assessment it names."""

        return self.assessment_value(text=text, assessment=AuditAssessment(text))

    def assessment_value(
        self, *, text: str, assessment: AuditAssessment, bold: bool = False
    ) -> str:
        """Style text according to an audit assessment."""

        style: TextStyle = self.theme.caution
        if assessment == AuditAssessment.READY:
            style = self.theme.ready
        elif assessment == AuditAssessment.NOT_READY:
            style = self.theme.not_ready
        prefix: str = ANSI_BOLD if bold else ""
        return TextStyle(prefix + style.prefix).apply(text=text, use_color=self.use_color)

    def diff_lines(self, diff_lines: tuple[str, ...]) -> list[str]:
        """Style unified-diff lines by their leading marker."""

        styled_lines: list[str] = []
        diff_line: str
        for diff_line in diff_lines:
            styled_lines.append(self._styled_diff_line(diff_line))
        return styled_lines

    def _styled_diff_line(self, diff_line: str) -> str:
        if diff_line.startswith(_DIFF_CONTEXT_PREFIXES):
            return self.theme.diff_context.apply(text=diff_line, use_color=self.use_color)
        if diff_line.startswith(_DIFF_ADDED_PREFIX):
            return self.theme.diff_added.apply(text=diff_line, use_color=self.use_color)
        if diff_line.startswith(_DIFF_REMOVED_PREFIX):
            return self.theme.diff_removed.apply(text=diff_line, use_color=self.use_color)
        return diff_line

    def muted(self, text: str) -> str:
        """Style de-emphasised text."""

        return self.theme.muted.apply(text=text, use_color=self.use_color)

    def muted_strong(self, text: str) -> str:
        """Style de-emphasised heading text."""

        return self.theme.muted_strong.apply(text=text, use_color=self.use_color)

    def passed(self, text: str) -> str:
        """Style text representing a passing result."""

        return self.theme.passed.apply(text=text, use_color=self.use_color)

    def failed(self, text: str) -> str:
        """Style text representing a failing result."""

        return self.theme.failed.apply(text=text, use_color=self.use_color)

    def outcome(self, *, text: str, passed: bool) -> str:
        """Style an outcome word by whether it passed."""

        style: TextStyle = self.theme.passed_strong if passed else self.theme.failed_strong
        return style.apply(text=text, use_color=self.use_color)
