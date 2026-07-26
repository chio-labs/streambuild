"""Custom exceptions for transform SQL contract validation."""


class PipelineCompileError(ValueError):
    """Raised when pipeline compilation input or state is invalid."""


class TransformSqlContractError(Exception):
    """Base error for transform SQL contract validation failures."""

    def __init__(self, transform_name: str) -> None:
        super().__init__(transform_name)
        self.transform_name: str = transform_name


class TransformSqlParseError(TransformSqlContractError):
    """Raised when transform SQL cannot be parsed."""

    def __init__(self, transform_name: str, query: str, details: str) -> None:
        super().__init__(transform_name)
        self.query: str = query
        self.details: str = details

    def __str__(self) -> str:
        return (
            f"Transform '{self.transform_name}' contains invalid SQL and could not be parsed: "
            f"{self.details}"
        )


class TransformSqlMultipleStatementsError(TransformSqlContractError):
    """Raised when transform SQL contains multiple statements."""

    def __init__(self, transform_name: str, statement_count: int) -> None:
        super().__init__(transform_name)
        self.statement_count: int = statement_count

    def __str__(self) -> str:
        return (
            f"Transform '{self.transform_name}' must contain exactly one SQL statement, "
            f"but found {self.statement_count}."
        )


class TransformSqlFinalQueryShapeError(TransformSqlContractError):
    """Raised when transform SQL does not expose one outermost final SELECT."""

    def __init__(self, transform_name: str, statement_type: str) -> None:
        super().__init__(transform_name)
        self.statement_type: str = statement_type

    def __str__(self) -> str:
        return (
            f"Transform '{self.transform_name}' must end in one outermost SELECT that defines "
            f"the output schema, but found top-level statement type '{self.statement_type}'."
        )


class TransformSqlTopLevelSetOperationError(TransformSqlContractError):
    """Raised when transform SQL uses a top-level set operation."""

    def __init__(self, transform_name: str, statement_sql: str) -> None:
        super().__init__(transform_name)
        self.statement_sql: str = statement_sql

    def __str__(self) -> str:
        return (
            f"Transform '{self.transform_name}' must end in one outermost SELECT that defines "
            "the output schema. Top-level set operations like UNION or UNION ALL are not "
            "allowed. Move the set operation into a CTE or subquery, then add a final SELECT "
            "with typed projections like CAST(expr AS Type) AS name or expr::Type AS name."
        )


class TransformSqlStarProjectionError(TransformSqlContractError):
    """Raised when the outermost projection uses '*'."""

    def __init__(self, transform_name: str, column_index: int) -> None:
        super().__init__(transform_name)
        self.column_index: int = column_index

    def __str__(self) -> str:
        return (
            f"Transform '{self.transform_name}' has an invalid output contract at column "
            f"{self.column_index}. Wildcard projections like '*' are not allowed in the outermost "
            "SELECT. Use explicit typed projections like CAST(expr AS Type) AS name or "
            "expr::Type AS name."
        )


class TransformSqlDuplicateAliasError(TransformSqlContractError):
    """Raised when the outermost projection repeats an output alias."""

    def __init__(self, transform_name: str, alias: str) -> None:
        super().__init__(transform_name)
        self.alias: str = alias

    def __str__(self) -> str:
        return (
            f"Transform '{self.transform_name}' has an invalid output contract. "
            f"Duplicate outermost SELECT alias '{self.alias}' is not allowed. "
            "Each derived output column must appear exactly once."
        )


class TransformSqlUntypedProjectionError(TransformSqlContractError):
    """Raised when an outermost projection is not an explicitly typed alias."""

    def __init__(self, transform_name: str, column_index: int, projection_sql: str) -> None:
        super().__init__(transform_name)
        self.column_index: int = column_index
        self.projection_sql: str = projection_sql

    def __str__(self) -> str:
        return (
            f"Transform '{self.transform_name}' has an invalid output contract at column "
            f"{self.column_index}. Expected outermost projection {self.column_index} to use "
            "an explicit typed alias like CAST(expr AS Type) AS name or expr::Type AS name, "
            "but found "
            f"`{self.projection_sql}`."
        )


class TransformOrderByUnknownColumnError(TransformSqlContractError):
    """Raised when an ORDER BY expression references unknown derived columns."""

    def __init__(
        self,
        transform_name: str,
        expression: str,
        unknown_column_names: tuple[str, ...],
        available_column_names: tuple[str, ...],
    ) -> None:
        super().__init__(transform_name)
        self.expression: str = expression
        self.unknown_column_names: tuple[str, ...] = unknown_column_names
        self.available_column_names: tuple[str, ...] = available_column_names

    def __str__(self) -> str:
        unknown_column_names: str = ", ".join(self.unknown_column_names)
        available_column_names: str = ", ".join(self.available_column_names)
        return (
            f"Transform '{self.transform_name}' has an invalid ORDER BY expression "
            f"`{self.expression}`. Referenced output columns not found in the derived schema: "
            f"{unknown_column_names}. Available columns: {available_column_names}."
        )


class TransformPartitionByUnknownColumnError(TransformSqlContractError):
    """Raised when a PARTITION BY expression references unknown derived columns."""

    def __init__(
        self,
        transform_name: str,
        expression: str,
        unknown_column_names: tuple[str, ...],
        available_column_names: tuple[str, ...],
    ) -> None:
        super().__init__(transform_name)
        self.expression: str = expression
        self.unknown_column_names: tuple[str, ...] = unknown_column_names
        self.available_column_names: tuple[str, ...] = available_column_names

    def __str__(self) -> str:
        unknown_column_names: str = ", ".join(self.unknown_column_names)
        available_column_names: str = ", ".join(self.available_column_names)
        return (
            f"Transform '{self.transform_name}' has an invalid PARTITION BY expression "
            f"`{self.expression}`. Referenced output columns not found in the derived schema: "
            f"{unknown_column_names}. Available columns: {available_column_names}."
        )


class TransformTtlUnknownColumnError(TransformSqlContractError):
    """Raised when a TTL expression references unknown derived columns."""

    def __init__(
        self,
        transform_name: str,
        expression: str,
        unknown_column_names: tuple[str, ...],
        available_column_names: tuple[str, ...],
    ) -> None:
        super().__init__(transform_name)
        self.expression: str = expression
        self.unknown_column_names: tuple[str, ...] = unknown_column_names
        self.available_column_names: tuple[str, ...] = available_column_names

    def __str__(self) -> str:
        unknown_column_names: str = ", ".join(self.unknown_column_names)
        available_column_names: str = ", ".join(self.available_column_names)
        return (
            f"Transform '{self.transform_name}' has an invalid TTL expression "
            f"`{self.expression}`. Referenced output columns not found in the derived schema: "
            f"{unknown_column_names}. Available columns: {available_column_names}."
        )
