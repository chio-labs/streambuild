"""Structured SQL analysis failures."""

from streambuild.compiler.sql_analysis.models import SqlSourceSpan


class SqlAnalysisError(ValueError):
    """Raised when SQL cannot be scanned, parsed, rewritten, or generated safely."""

    def __init__(self, message: str, *, span: SqlSourceSpan | None = None) -> None:
        super().__init__(message)
        self.span: SqlSourceSpan | None = span


class SqlMissingWithClauseError(SqlAnalysisError):
    """Raised when a statement expected to open with a WITH clause does not."""

    def __init__(self, *, context: str, span: SqlSourceSpan) -> None:
        super().__init__(f"{context} must declare CTEs in a WITH clause", span=span)
        self.context: str = context


class SqlStatementCountError(SqlAnalysisError):
    """Raised when authored model SQL does not contain exactly one statement."""

    def __init__(self, statement_count: int) -> None:
        super().__init__(f"Expected exactly one SQL statement; found {statement_count}")
        self.statement_count: int = statement_count


class SqlQueryShapeError(SqlAnalysisError):
    """Raised when the outer statement is not a supported model SELECT."""

    def __init__(self, *, statement_type: str, statement_sql: str, is_set_operation: bool) -> None:
        super().__init__(f"Unsupported outer SQL statement shape: {statement_type}")
        self.statement_type: str = statement_type
        self.statement_sql: str = statement_sql
        self.is_set_operation: bool = is_set_operation


class SqlStarProjectionError(SqlAnalysisError):
    """Raised when an outer model projection contains a wildcard."""

    def __init__(self, *, column_index: int, span: SqlSourceSpan) -> None:
        super().__init__(f"Wildcard output projection at column {column_index}", span=span)
        self.column_index: int = column_index


class SqlUntypedProjectionError(SqlAnalysisError):
    """Raised when an outer projection lacks an explicit alias and cast."""

    def __init__(self, *, column_index: int, projection_sql: str, span: SqlSourceSpan) -> None:
        super().__init__(f"Untyped output projection at column {column_index}", span=span)
        self.column_index: int = column_index
        self.projection_sql: str = projection_sql


class SqlDuplicateAliasError(SqlAnalysisError):
    """Raised when outer model projections repeat one output name."""

    def __init__(self, *, alias: str, span: SqlSourceSpan) -> None:
        super().__init__(f"Duplicate outer projection alias: {alias}", span=span)
        self.alias: str = alias


class SqlStorageReferenceError(SqlAnalysisError):
    """Raised when a storage expression references an unknown output column."""

    def __init__(
        self,
        *,
        kind: str,
        expression: str,
        unknown_column_names: tuple[str, ...],
        available_column_names: tuple[str, ...],
    ) -> None:
        message: str = f"Unknown model output columns in {kind}: {', '.join(unknown_column_names)}"
        super().__init__(message)
        self.kind: str = kind
        self.expression: str = expression
        self.unknown_column_names: tuple[str, ...] = unknown_column_names
        self.available_column_names: tuple[str, ...] = available_column_names
