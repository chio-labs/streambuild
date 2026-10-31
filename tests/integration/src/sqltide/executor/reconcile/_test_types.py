from dataclasses import dataclass


@dataclass(frozen=True)
class ReconcilePersistenceIntegrationTestCase:
    description: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_id_prefix_matches: tuple[bool, ...]
    expected_reconcile_id_prefix: str
