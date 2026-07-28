"""Split SQL extension header blocks through lexical analysis."""

from streambuild.compiler.sql_analysis._helpers.scanning import split_header_blocks
from streambuild.compiler.sql_analysis.models import SqlHeaderBlock


def split_sql_header_blocks(*, sql: str, keyword: str) -> tuple[SqlHeaderBlock, ...]:
    """Return line-leading extension headers and their SQL bodies."""

    return split_header_blocks(sql=sql, keyword=keyword)
