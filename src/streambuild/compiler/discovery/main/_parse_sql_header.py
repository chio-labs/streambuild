"""Public SQLBuild-style SQL header parser."""

from streambuild.compiler.discovery._helpers.model_header import parse_model_header


def parse_sql_header(*, header: str) -> dict[str, object]:
    """Parse a MODEL, AUDIT, or TEST header with the shared key-value grammar."""

    return parse_model_header(header=header)
