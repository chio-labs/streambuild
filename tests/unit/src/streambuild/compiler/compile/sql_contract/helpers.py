from streambuild.compiler.compile.models import Column


def build_expected_columns(*column_definitions: tuple[str, str]) -> tuple[Column, ...]:
    return tuple(Column(name=name, type=column_type) for name, column_type in column_definitions)
