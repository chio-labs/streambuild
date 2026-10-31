from dataclasses import dataclass


@dataclass(frozen=True)
class PostgresControlStoreTestCase:
    description: str
    expected_username: str
