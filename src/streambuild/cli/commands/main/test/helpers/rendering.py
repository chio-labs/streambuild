"""Rendering helpers for SQL-native test results."""

from __future__ import annotations

from pathlib import Path

from streambuild.cli.commands.main.shared.constants import (
    ANSI_BOLD,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_RED,
)
from streambuild.cli.commands.main.shared.helpers.styling import apply_style
from streambuild.cli.commands.main.test.constants import MAX_RENDERED_ROWS
from streambuild.cli.commands.main.test.models import PairedDiffSection
from streambuild.executor.testing.models import SqlTestExecutionResult, SqlTestTargetExecutionResult


def render_sql_test_results(
    *,
    results: tuple[SqlTestExecutionResult, ...],
    project_dir: Path,
    verbose: bool,
) -> str:
    """Render SQL-native test execution results for CLI output."""

    lines: list[str] = []
    failed_paths: list[Path] = []
    passed_count: int = sum(1 for result in results if result.passed)
    failed_count: int = len(results) - passed_count
    result_index: int
    result: SqlTestExecutionResult
    for result_index, result in enumerate(results):
        previous_result: SqlTestExecutionResult | None = (
            results[result_index - 1] if result_index > 0 else None
        )
        next_result: SqlTestExecutionResult | None = (
            results[result_index + 1] if result_index + 1 < len(results) else None
        )
        if result.passed and previous_result is not None and not previous_result.passed:
            lines.append("")
        if not result.passed and lines:
            lines.append("")
        relative_path: str = _render_result_label(
            file_path=result.file_path,
            name=result.name,
            test_index=result.test_index,
            project_dir=project_dir,
        )
        status: str = _style_status("PASS" if result.passed else "FAIL", passed=result.passed)
        lines.append(f"{status}  {_render_target_label(result)}  {relative_path}")
        if result.passed:
            continue
        if result.file_path not in failed_paths:
            failed_paths.append(result.file_path)
        lines.extend(_render_failed_result(result=result, verbose=verbose))
        if next_result is not None:
            lines.append("")
    summary_text: str = f"Results: {passed_count} passed, {failed_count} failed"
    lines.append(_style_summary(summary_text, has_failures=failed_count > 0))
    if failed_paths:
        lines.append("Failed:")
        failed_path: Path
        for failed_path in failed_paths:
            lines.append(f"  stb test {_render_result_path(failed_path, project_dir)}")
    return "\n".join(lines)


def _render_failed_result(
    *,
    result: SqlTestExecutionResult,
    verbose: bool,
) -> tuple[str, ...]:
    if len(result.target_results) > 1:
        lines: list[str] = []
        target_result: SqlTestTargetExecutionResult
        first_failed_target_rendered: bool = False
        for target_result in result.target_results:
            if target_result.passed:
                continue
            if first_failed_target_rendered:
                lines.append("")
            lines.append(f"  target: {target_result.target_model_name}")
            lines.extend(_render_target_failed_result(result=target_result, verbose=verbose))
            first_failed_target_rendered = True
        return tuple(lines)
    return _render_target_failed_result(result=result.target_results[0], verbose=verbose)


def _render_target_failed_result(
    *,
    result: SqlTestTargetExecutionResult,
    verbose: bool,
) -> tuple[str, ...]:
    paired_sections, remaining_missing_rows, remaining_unexpected_rows = (
        _build_paired_diff_sections(result=result)
    )
    lines: list[str] = []
    if paired_sections:
        differing_row_count: int = sum(section.paired_row_count for section in paired_sections)
        row_label: str = "row differs" if differing_row_count == 1 else "rows differ"
        lines.append(f"  diff ({differing_row_count} {row_label}):")
        lines.append(f"  columns: {', '.join(result.column_names)}")
        section: PairedDiffSection
        for section in paired_sections:
            lines.extend(_render_table_section(section=section, indent="  ", verbose=verbose))
    else:
        lines.append(
            "  diff summary: "
            f"{len(result.missing_rows)} missing, {len(result.unexpected_rows)} unexpected"
        )
        lines.append(f"  columns: {', '.join(result.column_names)}")
    if remaining_missing_rows:
        lines.extend(
            _render_table_section(
                section=PairedDiffSection(
                    title="missing rows",
                    headers=result.column_names,
                    rows=tuple(_stringify_row(row) for row in remaining_missing_rows),
                    paired_row_count=len(remaining_missing_rows),
                ),
                indent="  ",
                verbose=verbose,
            )
        )
    if remaining_unexpected_rows:
        lines.extend(
            _render_table_section(
                section=PairedDiffSection(
                    title="unexpected rows",
                    headers=result.column_names,
                    rows=tuple(_stringify_row(row) for row in remaining_unexpected_rows),
                    paired_row_count=len(remaining_unexpected_rows),
                ),
                indent="  ",
                verbose=verbose,
            )
        )
    return tuple(lines)


def _build_paired_diff_sections(
    *,
    result: SqlTestTargetExecutionResult,
) -> tuple[
    tuple[PairedDiffSection, ...], tuple[tuple[object, ...], ...], tuple[tuple[object, ...], ...]
]:
    remaining_missing_rows: list[tuple[object, ...]] = list(result.missing_rows)
    remaining_unexpected_rows: list[tuple[object, ...]] = list(result.unexpected_rows)
    paired_groups: dict[
        tuple[tuple[int, ...], tuple[int, ...]], list[tuple[tuple[object, ...], tuple[object, ...]]]
    ] = {}
    matched_missing_indices: set[int] = set()
    matched_unexpected_indices: set[int] = set()
    missing_index: int
    for missing_index, missing_row in enumerate(result.missing_rows):
        best_match_index: int | None = None
        best_match_score: int = -1
        best_key_indexes: tuple[int, ...] = ()
        best_diff_indexes: tuple[int, ...] = ()
        unexpected_index: int
        for unexpected_index, unexpected_row in enumerate(result.unexpected_rows):
            if unexpected_index in matched_unexpected_indices:
                continue
            key_indexes: tuple[int, ...] = tuple(
                index
                for index, (missing_value, unexpected_value) in enumerate(
                    zip(missing_row, unexpected_row, strict=True)
                )
                if missing_value == unexpected_value
            )
            diff_indexes: tuple[int, ...] = tuple(
                index
                for index, (missing_value, unexpected_value) in enumerate(
                    zip(missing_row, unexpected_row, strict=True)
                )
                if missing_value != unexpected_value
            )
            if not key_indexes or not diff_indexes:
                continue
            if len(key_indexes) > best_match_score:
                best_match_index = unexpected_index
                best_match_score = len(key_indexes)
                best_key_indexes = key_indexes
                best_diff_indexes = diff_indexes
        if best_match_index is None:
            continue
        matched_missing_indices.add(missing_index)
        matched_unexpected_indices.add(best_match_index)
        paired_groups.setdefault((best_key_indexes, best_diff_indexes), []).append(
            (missing_row, result.unexpected_rows[best_match_index])
        )
    paired_sections: list[PairedDiffSection] = []
    group_key: tuple[tuple[int, ...], tuple[int, ...]]
    paired_row_index: int = 1
    for group_key in sorted(paired_groups):
        key_indexes, diff_indexes = group_key
        rows: list[tuple[str, ...]] = []
        missing_row: tuple[object, ...]
        unexpected_row: tuple[object, ...]
        for missing_row, unexpected_row in paired_groups[group_key]:
            rendered_expected_row: list[str] = [str(paired_row_index), _style_expected("expected")]
            rendered_actual_row: list[str] = [str(paired_row_index), _style_actual("actual")]
            column_index: int
            for column_index in range(len(result.column_names)):
                expected_value: str = _stringify_value(missing_row[column_index])
                actual_value: str = _stringify_value(unexpected_row[column_index])
                if column_index in diff_indexes:
                    rendered_expected_row.append(_style_expected(expected_value))
                    rendered_actual_row.append(_style_actual(actual_value))
                    continue
                if column_index in key_indexes:
                    rendered_expected_row.append(_style_key_value(expected_value))
                    rendered_actual_row.append(_style_key_value(actual_value))
                    continue
                rendered_expected_row.append(expected_value)
                rendered_actual_row.append(actual_value)
            rows.append(tuple(rendered_expected_row))
            rows.append(tuple(rendered_actual_row))
            paired_row_index += 1
        headers: tuple[str, ...] = ("row", "state", *result.column_names)
        paired_sections.append(
            PairedDiffSection(
                title="",
                headers=headers,
                rows=tuple(rows),
                paired_row_count=len(paired_groups[group_key]),
            )
        )
    return (
        tuple(paired_sections),
        tuple(
            row
            for index, row in enumerate(remaining_missing_rows)
            if index not in matched_missing_indices
        ),
        tuple(
            row
            for index, row in enumerate(remaining_unexpected_rows)
            if index not in matched_unexpected_indices
        ),
    )


def _render_table_section(
    *,
    section: PairedDiffSection,
    indent: str,
    verbose: bool,
) -> tuple[str, ...]:
    rendered_rows: tuple[tuple[str, ...], ...]
    hidden_count: int
    rendered_rows, hidden_count = _truncate_rows(section.rows, verbose=verbose)
    lines: list[str] = []
    if section.title:
        title_suffix: str = f" ({len(section.rows)})"
        if hidden_count:
            title_suffix = f" ({len(section.rows)}, showing first {len(rendered_rows)})"
        lines.append(f"{indent}{section.title}{title_suffix}:")
    widths: tuple[int, ...] = _compute_column_widths(
        headers=section.headers,
        rows=rendered_rows,
    )
    lines.append(f"{indent}  {_render_table_row(section.headers, widths=widths, header=True)}")
    row: tuple[str, ...]
    for row in rendered_rows:
        lines.append(f"{indent}  {_render_table_row(row, widths=widths, header=False)}")
    if hidden_count:
        hidden_rows_message: str = apply_style(
            f"({hidden_count} more rows not shown, run with --verbose to see all)",
            ANSI_DIM,
        )
        lines.append(f"{indent}  {hidden_rows_message}")
    return tuple(lines)


def _truncate_rows(
    rows: tuple[tuple[str, ...], ...],
    *,
    verbose: bool,
) -> tuple[tuple[tuple[str, ...], ...], int]:
    if verbose or len(rows) <= MAX_RENDERED_ROWS:
        return rows, 0
    return rows[:MAX_RENDERED_ROWS], len(rows) - MAX_RENDERED_ROWS


def _compute_column_widths(
    *,
    headers: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
) -> tuple[int, ...]:
    widths: list[int] = [len(_strip_ansi(header)) for header in headers]
    row: tuple[str, ...]
    for row in rows:
        index: int
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(_strip_ansi(cell)))
    return tuple(widths)


def _render_table_row(
    row: tuple[str, ...],
    *,
    widths: tuple[int, ...],
    header: bool,
) -> str:
    rendered_cells: list[str] = []
    index: int
    for index, cell in enumerate(row):
        padding_width: int = widths[index] - len(_strip_ansi(cell))
        padded_cell: str = cell + (" " * padding_width)
        rendered_cells.append(_style_headers(padded_cell) if header else padded_cell)
    return "  ".join(rendered_cells)


def _stringify_row(row: tuple[object, ...]) -> tuple[str, ...]:
    return tuple(_stringify_value(value) for value in row)


def _stringify_value(value: object) -> str:
    if value is None:
        return "NULL"
    return str(value)


def _render_result_path(file_path: Path, project_dir: Path) -> str:
    try:
        return file_path.relative_to(project_dir).as_posix()
    except ValueError:
        return str(file_path)


def _render_result_label(
    *,
    file_path: Path,
    name: str | None,
    test_index: int,
    project_dir: Path,
) -> str:
    relative_path: str = _render_result_path(file_path, project_dir)
    if name is not None:
        return f"{relative_path}  [{name}]"
    if test_index == 1:
        return relative_path
    return f"{relative_path}::{test_index}"


def _render_target_label(result: SqlTestExecutionResult) -> str:
    target_model_names: tuple[str, ...] = tuple(
        target_result.target_model_name for target_result in result.target_results
    )
    if len(target_model_names) == 1:
        return target_model_names[0]
    return ", ".join(target_model_names)


def _style_status(text: str, *, passed: bool) -> str:
    return apply_style(text, ANSI_GREEN if passed else ANSI_RED, ANSI_BOLD)


def _style_summary(text: str, *, has_failures: bool) -> str:
    return apply_style(text, ANSI_RED if has_failures else ANSI_GREEN, ANSI_BOLD)


def _style_headers(text: str) -> str:
    return apply_style(text, ANSI_DIM, ANSI_BOLD)


def _style_expected(text: str) -> str:
    return apply_style(text, ANSI_GREEN)


def _style_actual(text: str) -> str:
    return apply_style(text, ANSI_RED)


def _style_key_value(text: str) -> str:
    return apply_style(text, ANSI_DIM)


def _strip_ansi(text: str) -> str:
    result: str = text
    result = result.replace("\033[0m", "")
    result = result.replace("\033[1m", "")
    result = result.replace("\033[2m", "")
    result = result.replace("\033[31m", "")
    result = result.replace("\033[32m", "")
    result = result.replace("\033[33m", "")
    result = result.replace("\033[34m", "")
    return result
