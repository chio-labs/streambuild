from dataclasses import dataclass


@dataclass(frozen=True)
class ExpandProjectSqlMacrosTestCase:
    description: str
    macro_file_name: str
    macro_file_contents: str
    sql_body: str
    expected_expanded_fragment: str


@dataclass(frozen=True)
class ExpandProjectSqlMacrosErrorTestCase:
    description: str
    macro_file_name: str
    macro_file_contents: str
    sql_body: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ExpandProjectSqlMacrosCollisionTestCase:
    description: str
    first_macro_file_name: str
    first_macro_file_contents: str
    second_macro_file_name: str
    second_macro_file_contents: str
    sql_body: str
    expected_error_fragment: str
