from dataclasses import dataclass


@dataclass(frozen=True)
class ClickHouseClientIntegrationTestCase:
    description: str
    inserted_rows: tuple[dict[str, object], ...]
    expected_rows: tuple[tuple[object, ...], ...]
