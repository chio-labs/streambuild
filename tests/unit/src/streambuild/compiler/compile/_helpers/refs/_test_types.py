from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractRefsTestCase:
    description: str
    sql: str
    expected_refs: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True)
class ReplaceRefsTestCase:
    description: str
    sql: str
    resolver: dict[str, str]
    expected_sql_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReplaceRefsErrorTestCase:
    description: str
    sql: str
    resolver: dict[str, str]
    expected_error_type: type[Exception]
    expected_error_fragment: str


@dataclass(frozen=True)
class ExtractRefsErrorTestCase:
    description: str
    sql: str
    expected_error_type: type[Exception]
    expected_error_fragment: str
