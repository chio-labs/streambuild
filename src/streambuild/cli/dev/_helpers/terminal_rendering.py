"""Render the dev server's terminal voice: startup banner and activity lines."""

from __future__ import annotations

from pathlib import Path

from streambuild.cli.presentation.classes.cli_style import CliStyle
from streambuild.dev_server.models import CompileOutcome
from streambuild.dev_server.types import ActivityTone, CompileStateKind

_FACT_LABEL_WIDTH: int = 9
_FACT_VALUE_INDENT: str = " " * (2 + _FACT_LABEL_WIDTH + 2)
_CATEGORY_COLUMN_WIDTH: int = 6
_STATUS_COLUMN_WIDTH: int = 9
_SEPARATOR: str = " · "


def startup_lines(
    *,
    style: CliStyle,
    outcome: CompileOutcome,
    project_dir: Path,
    database: str | None,
    host: str,
    port: int,
    tool_version: str,
) -> tuple[str, ...]:
    """Build the startup banner: dim labels, colored state words, plain facts."""

    base_url: str = f"http://{host}:{port}"
    return (
        f"{style.title('StreamBuild dev server')} {style.muted('v' + tool_version)}",
        "",
        _fact_line(style=style, label="project", value=project_dir.name),
        _fact_line(
            style=style, label="compile", value=_compile_value(style=style, outcome=outcome)
        ),
        *_compile_error_lines(style=style, outcome=outcome),
        _fact_line(
            style=style, label="warehouse", value=_warehouse_value(style=style, database=database)
        ),
        "",
        _fact_line(style=style, label="ui", value=base_url),
        _fact_line(style=style, label="api", value=f"{base_url}/api"),
        "",
        f"  {style.muted('ctrl+c to stop')}",
        "",
    )


def reload_summary(*, outcome: CompileOutcome) -> tuple[str, ActivityTone, str]:
    """Reduce one reload outcome to an activity (status, tone, detail) triple."""

    if outcome.state == CompileStateKind.OK:
        return "ok", ActivityTone.GOOD, _compile_counts(outcome=outcome)
    message: str = outcome.error.message if outcome.error is not None else "compile failed"
    return "failing", ActivityTone.BAD, message


def activity_line(
    *,
    style: CliStyle,
    timestamp: str,
    category: str,
    status: str,
    tone: ActivityTone,
    detail: str,
) -> str:
    """Build one aligned activity line: dim time, bold category, toned status."""

    category_text: str = style.subsection(category.ljust(_CATEGORY_COLUMN_WIDTH))
    status_text: str = _toned(style=style, text=status.ljust(_STATUS_COLUMN_WIDTH), tone=tone)
    return f"{style.muted(timestamp)}  {category_text}  {status_text}  {detail}".rstrip()


def _fact_line(*, style: CliStyle, label: str, value: str) -> str:
    return f"  {style.label(label.ljust(_FACT_LABEL_WIDTH))}  {value}"


def _compile_value(*, style: CliStyle, outcome: CompileOutcome) -> str:
    if outcome.state != CompileStateKind.OK:
        return style.outcome(text="failing", passed=False)
    ok_text: str = style.outcome(text="ok", passed=True)
    counts: str = _compile_counts(outcome=outcome)
    return f"{ok_text}{_SEPARATOR}{counts}" if counts else ok_text


def _compile_counts(*, outcome: CompileOutcome) -> str:
    if outcome.analysis is None:
        return ""
    models: str = _counted(count=len(outcome.analysis.compiled_project.models), noun="model")
    sources: str = _counted(count=len(outcome.analysis.compiled_project.sources), noun="source")
    counts: str = f"{models}{_SEPARATOR}{sources}"
    if outcome.timings is None:
        return counts
    total_ms: int = (
        outcome.timings.discovery_ms
        + outcome.timings.compile_inputs_ms
        + outcome.timings.assembly_ms
        + outcome.timings.graph_ms
        + outcome.timings.realization_ms
    )
    return f"{counts}{_SEPARATOR}{total_ms}ms"


def _compile_error_lines(*, style: CliStyle, outcome: CompileOutcome) -> tuple[str, ...]:
    if outcome.error is None:
        return ()
    location: str = ""
    if outcome.error.path is not None:
        location = f"{outcome.error.path}:{outcome.error.line}:{outcome.error.column}"
    prefix: str = (
        f"{_FACT_VALUE_INDENT}{style.muted(location)}  " if location else _FACT_VALUE_INDENT
    )
    return (f"{prefix}{outcome.error.message}",)


def _counted(*, count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _warehouse_value(*, style: CliStyle, database: str | None) -> str:
    if database is None:
        return style.warning("not connected")
    return f"{style.passed('connected')}{_SEPARATOR}{database}"


def _toned(*, style: CliStyle, text: str, tone: ActivityTone) -> str:
    if tone == ActivityTone.GOOD:
        return style.passed(text)
    if tone == ActivityTone.BAD:
        return style.failed(text)
    if tone == ActivityTone.CAUTION:
        return style.warning(text)
    return text
