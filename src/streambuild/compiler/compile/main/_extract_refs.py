"""Extract logical source and model refs from model SQL."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.compile.models import ParsedRef
from streambuild.compiler.discovery.types import RefType
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.main._extract_references import extract_references
from streambuild.compiler.sql_analysis.models import SqlReference
from streambuild.diagnostics.models import SourceLocation


def extract_refs(
    *,
    sql: str,
    source_path: Path | None = None,
    source_line: int = 1,
    source_column: int = 1,
) -> list[ParsedRef]:
    """Return parsed logical node refs referenced by `__source(...)` and `__ref(...)`."""

    try:
        references: tuple[SqlReference, ...] = extract_references(sql)
    except SqlAnalysisError as error:
        location: SourceLocation | None = (
            None
            if source_path is None or error.span is None
            else _source_location(
                source_path=source_path,
                source_line=source_line,
                source_column=source_column,
                relative_line=error.span.line,
                relative_column=error.span.column,
                relative_end_line=error.span.end_line,
                relative_end_column=error.span.end_column,
            )
        )
        raise PipelineCompileError(str(error), span=error.span, location=location) from None
    return [
        ParsedRef(
            name=reference.name,
            relation_type=reference.relation_type,
            ref_type=None if reference.ref_type is None else RefType(reference.ref_type),
            span=reference.span,
        )
        for reference in references
    ]


def _source_location(
    *,
    source_path: Path,
    source_line: int,
    source_column: int,
    relative_line: int,
    relative_column: int,
    relative_end_line: int,
    relative_end_column: int,
) -> SourceLocation:
    line: int = source_line + relative_line - 1
    end_line: int = source_line + relative_end_line - 1
    column: int = source_column + relative_column - 1 if relative_line == 1 else relative_column
    end_column: int = (
        source_column + relative_end_column - 1 if relative_end_line == 1 else relative_end_column
    )
    return SourceLocation(
        path=source_path,
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
    )
