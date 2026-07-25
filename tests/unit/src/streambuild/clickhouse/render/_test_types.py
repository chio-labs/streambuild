from dataclasses import dataclass


@dataclass(frozen=True)
class RenderDesiredStateDdlTestCase:
    description: str
    database: str
    expected_rendered_keys: tuple[tuple[str | None, str, str], ...]
    expected_statement_fragments: tuple[str, ...]
