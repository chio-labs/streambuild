"""Target-scoped mutation locking for warehouse operations."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterTargetMutationLock


@contextmanager
def target_mutation_lock(*, connection: AdapterConnection, database: str) -> Iterator[None]:
    """Hold exclusive target mutation ownership for one operation."""

    lock: AdapterTargetMutationLock = connection.acquire_target_mutation_lock(
        database=database,
        owner_id=str(uuid4()),
    )
    try:
        yield
    finally:
        connection.release_target_mutation_lock(lock)
