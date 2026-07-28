from dataclasses import dataclass


@dataclass(frozen=True)
class ReciprocalOwnershipDatabaseTestCase:
    description: str
    ownership_database_name: str
    target_database: str
    expected_metadata_reads: tuple[str, ...]


@dataclass(frozen=True)
class ReciprocalOwnershipRejectionTestCase:
    description: str
    database_name: str
    expected_error_fragment: str
