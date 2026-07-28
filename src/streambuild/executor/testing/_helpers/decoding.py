"""Decode one adapter bag-comparison result into directional row details."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.executor.testing.constants import (
    COMPARISON_CASE_INDEX,
    COMPARISON_DIFF_TYPE_INDEX,
    COMPARISON_MULTIPLICITY_INDEX,
    COMPARISON_ROW_LENGTH,
    COMPARISON_ROW_VALUES_INDEX,
    MISSING_DIFF_TYPE,
    UNEXPECTED_DIFF_TYPE,
)
from streambuild.executor.testing.exceptions import SqlTestExecutionError
from streambuild.executor.testing.models import ComparisonRows


@dataclass(frozen=True)
class _ComparisonRow:
    """One decoded comparison row and its multiplicity."""

    case_index: int
    diff_type: str
    values: tuple[object, ...]
    multiplicity: int


def decode_comparison_rows(
    *, rows: tuple[tuple[object, ...], ...], case_count: int, file_path: Path
) -> ComparisonRows:
    """Expand grouped multiplicities into per-case missing and unexpected rows."""

    missing: list[list[tuple[object, ...]]] = [[] for _index in range(case_count)]
    unexpected: list[list[tuple[object, ...]]] = [[] for _index in range(case_count)]
    raw_row: tuple[object, ...]
    for raw_row in rows:
        decoded: _ComparisonRow = _decode_row(
            raw_row=raw_row, case_count=case_count, file_path=file_path
        )
        destination: list[list[tuple[object, ...]]] = _destination(
            diff_type=decoded.diff_type,
            missing=missing,
            unexpected=unexpected,
            file_path=file_path,
        )
        destination[decoded.case_index].extend(
            decoded.values for _occurrence in range(decoded.multiplicity)
        )
    return ComparisonRows(
        missing=tuple(tuple(case_rows) for case_rows in missing),
        unexpected=tuple(tuple(case_rows) for case_rows in unexpected),
    )


def _destination(
    *,
    diff_type: str,
    missing: list[list[tuple[object, ...]]],
    unexpected: list[list[tuple[object, ...]]],
    file_path: Path,
) -> list[list[tuple[object, ...]]]:
    if diff_type == MISSING_DIFF_TYPE:
        return missing
    if diff_type == UNEXPECTED_DIFF_TYPE:
        return unexpected
    raise SqlTestExecutionError(
        f"SQL test query for '{file_path}' returned unsupported diff type '{diff_type}'"
    )


def _decode_row(*, raw_row: tuple[object, ...], case_count: int, file_path: Path) -> _ComparisonRow:
    if len(raw_row) != COMPARISON_ROW_LENGTH:
        raise _invalid_row(file_path)
    case_index: object = raw_row[COMPARISON_CASE_INDEX]
    diff_type: object = raw_row[COMPARISON_DIFF_TYPE_INDEX]
    row_values: object = raw_row[COMPARISON_ROW_VALUES_INDEX]
    multiplicity: object = raw_row[COMPARISON_MULTIPLICITY_INDEX]
    if (
        isinstance(case_index, bool)
        or not isinstance(case_index, int)
        or isinstance(multiplicity, bool)
        or not isinstance(multiplicity, int)
        or not isinstance(diff_type, str)
        or not isinstance(row_values, list | tuple)
        or not 0 <= case_index < case_count
        or multiplicity <= 0
    ):
        raise _invalid_row(file_path)
    return _ComparisonRow(
        case_index=case_index,
        diff_type=diff_type,
        values=tuple(row_values),
        multiplicity=multiplicity,
    )


def _invalid_row(file_path: Path) -> SqlTestExecutionError:
    return SqlTestExecutionError(
        f"SQL test query for '{file_path}' returned an invalid comparison row"
    )
