from dataclasses import dataclass

from streambuild.compiler.compile.models import Column


@dataclass(frozen=True)
class DeriveTransformOutputColumnsSuccessTestCase:
    description: str
    query: str
    expected_columns: tuple[Column, ...]


@dataclass(frozen=True)
class DeriveTransformOutputColumnsErrorTestCase:
    description: str
    query: str
    expected_error_type: type[Exception]
    expected_message_fragments: tuple[str, ...]
    expected_error_attributes: dict[str, object]


@dataclass(frozen=True)
class ValidateOrderByExpressionsTestCase:
    description: str
    order_by: tuple[str, ...]
    available_columns: tuple[Column, ...]
    expected_error_type: type[Exception] | None
    expected_message_fragments: tuple[str, ...]
    expected_error_attributes: dict[str, object]


@dataclass(frozen=True)
class ValidateSingleStorageExpressionTestCase:
    description: str
    expression: str | None
    available_columns: tuple[Column, ...]
    expected_error_type: type[Exception] | None
    expected_message_fragments: tuple[str, ...]
    expected_error_attributes: dict[str, object]
