"""Retain truthful warehouse health across temporary diagnostic failures."""

from dataclasses import replace

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterWarehouseHealth
from streambuild.adapter.types import AdapterWarehouseHealthAvailability


class WarehouseHealthReader:
    """Preserve the last usable snapshot while marking failed refreshes stale."""

    def __init__(self) -> None:
        self._last_usable_by_target: dict[tuple[str, str], AdapterWarehouseHealth] = {}

    def read(
        self, *, connection: AdapterConnection, database: str, measured_at: str
    ) -> AdapterWarehouseHealth:
        """Read diagnostics and retain explicit failure semantics."""

        target: tuple[str, str] = (connection.adapter_identity.name, database)
        try:
            current: AdapterWarehouseHealth = connection.load_warehouse_health(database)
        except Exception:
            current = AdapterWarehouseHealth(
                availability="unavailable",
                status="unknown",
                version=None,
                uptime_seconds=None,
                disks=(),
                inode_total=None,
                inode_free=None,
                inode_status="unknown",
                memory=None,
                activity=None,
                tables=None,
                collection_duration_ms=0,
                warnings=("Warehouse diagnostics are unavailable.",),
            )
        if current.availability is not AdapterWarehouseHealthAvailability.UNAVAILABLE:
            measured: AdapterWarehouseHealth = replace(current, measured_at=measured_at)
            self._last_usable_by_target[target] = measured
            return measured
        last_usable: AdapterWarehouseHealth | None = self._last_usable_by_target.get(target)
        if last_usable is None:
            return replace(current, measured_at=measured_at)
        return replace(
            last_usable,
            availability=AdapterWarehouseHealthAvailability.PARTIAL,
            warnings=current.warnings,
            stale=True,
        )
