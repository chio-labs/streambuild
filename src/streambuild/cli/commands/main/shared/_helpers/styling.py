"""Shared CLI styling and small formatting helpers for main commands."""

from __future__ import annotations

import os
import sys

from streambuild.cli.commands.main.shared.constants import (
    ANSI_BLUE,
    ANSI_BOLD,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_RED,
    ANSI_RESET,
    ANSI_YELLOW,
)
from streambuild.executor.audit_backfill.types import AuditAssessment


def format_bool(value: bool) -> str:
    return "yes" if value else "no"


def format_count(value: int | None) -> str:
    if value is None:
        return "n/a"
    return str(value)


def humanize_deployment_status(value: str) -> str:
    status_by_value: dict[str, str] = {
        "backfilling": "backfilling",
        "published": "published",
        "failed": "failed",
        "unknown": "unknown",
    }
    return status_by_value.get(value, value)


def humanize_timestamp(value: str) -> str:
    normalized: str = value.replace(" ", "T")
    if normalized.endswith("Z"):
        return normalized
    return f"{normalized}Z"


def format_percentage(value: float) -> str:
    return f"{value * 100:.1f}%"


def format_range(min_value: str | None, max_value: str | None) -> str:
    if min_value is None and max_value is None:
        return "n/a"
    return f"{min_value or 'n/a'} .. {max_value or 'n/a'}"


def style_diff_lines(diff_lines: tuple[str, ...]) -> list[str]:
    styled_lines: list[str] = []
    diff_line: str
    for diff_line in diff_lines:
        if diff_line.startswith("+++") or diff_line.startswith("---") or diff_line.startswith("@@"):
            styled_lines.append(apply_style(diff_line, ANSI_DIM))
            continue
        if diff_line.startswith("+"):
            styled_lines.append(apply_style(diff_line, ANSI_GREEN))
            continue
        if diff_line.startswith("-"):
            styled_lines.append(apply_style(diff_line, ANSI_RED))
            continue
        styled_lines.append(diff_line)
    return styled_lines


def style_title(text: str) -> str:
    return apply_style(text, ANSI_BOLD, ANSI_BLUE)


def style_section(text: str) -> str:
    return apply_style(f"{text}:", ANSI_BOLD, ANSI_BLUE)


def style_subsection(text: str) -> str:
    return apply_style(text, ANSI_BOLD)


def style_label(text: str) -> str:
    return apply_style(text, ANSI_DIM)


def style_label_value(label: str, value: str) -> str:
    return f"{style_label(label)}: {value}"


def style_object_name(text: str, *, assessment: AuditAssessment | None = None) -> str:
    if assessment is None:
        return apply_style(text, ANSI_BOLD)
    return style_assessment_value(text, assessment, bold=True)


def style_warning(text: str) -> str:
    return apply_style(text, ANSI_YELLOW)


def style_assessment(text: str) -> str:
    return style_assessment_value(text, AuditAssessment(text))


def style_assessment_value(text: str, assessment: AuditAssessment, *, bold: bool = False) -> str:
    style_codes: tuple[str, ...] = (ANSI_BOLD,) if bold else ()
    if assessment == AuditAssessment.READY:
        return apply_style(text, *style_codes, ANSI_GREEN)
    if assessment == AuditAssessment.NOT_READY:
        return apply_style(text, *style_codes, ANSI_RED)
    return apply_style(text, *style_codes, ANSI_YELLOW)


def apply_style(text: str, *codes: str) -> str:
    if not color_enabled() or not text:
        return text
    return f"{''.join(codes)}{text}{ANSI_RESET}"


def color_enabled() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("CLICOLOR_FORCE") == "1" or os.getenv("FORCE_COLOR") == "1":
        return True
    return sys.stdout.isatty()
