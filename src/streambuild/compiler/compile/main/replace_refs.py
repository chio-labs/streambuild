"""Replace logical ref markers in SQL with resolved relation names."""

from __future__ import annotations

from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.sql_analysis.classes.sql_reference_rewriter import (
    SqlReferenceRewriter,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError


def replace_refs(*, sql: str, resolver: dict[str, str], rewriter: SqlReferenceRewriter) -> str:
    """Replace logical refs with resolved SQL relation surfaces."""

    try:
        return rewriter.rewrite(sql=sql, resolver=resolver)
    except SqlAnalysisError as error:
        raise PipelineCompileError(str(error), span=error.span) from None
