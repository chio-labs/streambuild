"""Read bounded ClickHouse system-table diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import (
    AdapterWarehouseActivity,
    AdapterWarehouseDisk,
    AdapterWarehouseHealth,
    AdapterWarehouseMemory,
    AdapterWarehouseTable,
)
from streambuild.adapter.types import AdapterWarehouseHealthStatus
from streambuild.adapters.clickhouse.constants import (
    CLICKHOUSE_CAPACITY_CRITICAL_AVAILABLE_FRACTION,
    CLICKHOUSE_CAPACITY_WARNING_AVAILABLE_FRACTION,
)


class ClickHouseWarehouseHealthReader:
    """Read one bounded diagnostic snapshot from ClickHouse system tables."""

    def __init__(self, *, connection: AdapterConnection) -> None:
        self._connection: AdapterConnection = connection

    def read(self, *, database: str) -> AdapterWarehouseHealth:
        """Collect diagnostics without making optional failures authoritative."""

        return _load_clickhouse_warehouse_health(connection=self._connection, database=database)


def _load_clickhouse_warehouse_health(
    *, connection: AdapterConnection, database: str
) -> AdapterWarehouseHealth:
    """Collect one bounded snapshot without making optional failures authoritative."""

    started_at: float = perf_counter()
    warnings: list[str] = []
    try:
        disks: tuple[AdapterWarehouseDisk, ...] = _read_disks(connection)
        if not disks:
            return _unavailable(started_at=started_at)
        if all(
            AdapterWarehouseHealthStatus(disk.status) is AdapterWarehouseHealthStatus.UNKNOWN
            for disk in disks
        ):
            warnings.append("Usable disk capacity is unavailable.")
    except (AdapterError, KeyError, TypeError, ValueError):
        return _unavailable(started_at=started_at)

    version: str | None = None
    uptime_seconds: int | None = None
    inode_total: int | None = None
    inode_free: int | None = None
    inode_status: AdapterWarehouseHealthStatus = AdapterWarehouseHealthStatus.UNKNOWN
    memory: AdapterWarehouseMemory | None = None
    activity: AdapterWarehouseActivity | None = None
    tables: tuple[AdapterWarehouseTable, ...] = ()

    try:
        server_row: Mapping[str, object] | None = connection.query_one(
            statement="SELECT version() AS version, uptime() AS uptime_seconds",
            decode=lambda row: row,
        )
        if server_row is not None:
            version = str(server_row["version"])
            uptime_seconds = int(str(server_row["uptime_seconds"]))
        else:
            warnings.append("Server identity is unavailable.")
    except (AdapterError, KeyError, TypeError, ValueError):
        warnings.append("Server identity is unavailable.")

    try:
        metric_rows: tuple[Mapping[str, object], ...] = connection.query_many(
            statement=_metrics_query(),
            decode=lambda row: row,
        )
        metrics: dict[str, float] = {
            str(row["metric"]): float(str(row["value"])) for row in metric_rows
        }
        inode_total = _integer_metric(metrics=metrics, name="FilesystemMainPathTotalINodes")
        inode_free = _integer_metric(metrics=metrics, name="FilesystemMainPathAvailableINodes")
        inode_status = _capacity_status(available=inode_free, total=inode_total)
        memory = _memory(metrics)
        if inode_status is AdapterWarehouseHealthStatus.UNKNOWN:
            warnings.append("Main-path inode metrics are unavailable.")
        if memory is None:
            warnings.append("Meaningful memory context is unavailable.")
    except (AdapterError, KeyError, TypeError, ValueError):
        warnings.append("Memory and inode metrics are unavailable.")

    try:
        activity_row: Mapping[str, object] | None = connection.query_one(
            statement=_activity_query(),
            decode=lambda row: row,
        )
        if activity_row is not None:
            activity = AdapterWarehouseActivity(
                active_queries=int(str(activity_row["active_queries"])),
                active_merges=int(str(activity_row["active_merges"])),
                incomplete_mutations=int(str(activity_row["incomplete_mutations"])),
            )
        else:
            warnings.append("Current warehouse activity is unavailable.")
    except (AdapterError, KeyError, TypeError, ValueError):
        warnings.append("Current warehouse activity is unavailable.")

    try:
        tables = connection.query_many(
            statement=_tables_query(database),
            decode=lambda row: AdapterWarehouseTable(
                name=str(row["table"]),
                rows=int(str(row["rows"])),
                bytes_on_disk=int(str(row["bytes_on_disk"])),
                active_parts=int(str(row["active_parts"])),
            ),
        )
    except (AdapterError, KeyError, TypeError, ValueError):
        warnings.append("Project table footprint is unavailable.")

    status: AdapterWarehouseHealthStatus = _overall_status(disks=disks, inode_status=inode_status)
    return AdapterWarehouseHealth(
        availability="partial" if warnings else "available",
        status=status,
        version=version,
        uptime_seconds=uptime_seconds,
        disks=disks,
        inode_total=inode_total,
        inode_free=inode_free,
        inode_status=inode_status,
        memory=memory,
        activity=activity,
        tables=tables,
        collection_duration_ms=_elapsed_ms(started_at),
        warnings=tuple(warnings),
    )


def _read_disks(connection: AdapterConnection) -> tuple[AdapterWarehouseDisk, ...]:
    return connection.query_many(
        statement=(
            "SELECT name, path, type, total_space, free_space, unreserved_space, "
            "keep_free_space FROM system.disks ORDER BY name"
        ),
        decode=lambda row: AdapterWarehouseDisk(
            name=str(row["name"]),
            path=str(row["path"]),
            disk_type=str(row["type"]),
            total_bytes=int(str(row["total_space"])),
            free_bytes=int(str(row["free_space"])),
            unreserved_bytes=int(str(row["unreserved_space"])),
            keep_free_bytes=int(str(row["keep_free_space"])),
            status=_capacity_status(
                available=int(str(row["unreserved_space"])),
                total=int(str(row["total_space"])),
            ),
        ),
    )


def _metrics_query() -> str:
    names: str = ", ".join(
        f"'{name}'"
        for name in (
            "MemoryResident",
            "CGroupMemoryUsed",
            "CGroupMemoryTotal",
            "OSMemoryTotal",
            "FilesystemMainPathAvailableINodes",
            "FilesystemMainPathTotalINodes",
        )
    )
    return f"SELECT metric, value FROM system.asynchronous_metrics WHERE metric IN ({names})"


def _activity_query() -> str:
    return (
        "SELECT "
        "(SELECT count() FROM system.processes WHERE query_id != currentQueryID()) "
        "AS active_queries, "
        "(SELECT count() FROM system.merges) AS active_merges, "
        "(SELECT count() FROM system.mutations WHERE NOT is_done) AS incomplete_mutations"
    )


def _tables_query(database: str) -> str:
    escaped_database: str = database.replace("'", "''")
    return (
        "SELECT table, sum(rows) AS rows, sum(bytes_on_disk) AS bytes_on_disk, "
        "count() AS active_parts FROM system.parts "
        f"WHERE active AND database = '{escaped_database}' GROUP BY table "
        "ORDER BY bytes_on_disk DESC, table LIMIT 10"
    )


def _integer_metric(*, metrics: Mapping[str, float], name: str) -> int | None:
    value: float | None = metrics.get(name)
    return None if value is None else int(value)


def _memory(metrics: Mapping[str, float]) -> AdapterWarehouseMemory | None:
    resident: int | None = _integer_metric(metrics=metrics, name="MemoryResident")
    host_total: int | None = _integer_metric(metrics=metrics, name="OSMemoryTotal")
    cgroup_used: int | None = _integer_metric(metrics=metrics, name="CGroupMemoryUsed")
    cgroup_total: int | None = _integer_metric(metrics=metrics, name="CGroupMemoryTotal")
    pressure_fraction: float | None = None
    if cgroup_used is not None and cgroup_total is not None and cgroup_total > 0:
        pressure_fraction = cgroup_used / cgroup_total
    fallback_available: bool = resident is not None and host_total is not None and host_total > 0
    if pressure_fraction is None and not fallback_available:
        return None
    return AdapterWarehouseMemory(
        resident_bytes=resident,
        host_total_bytes=host_total,
        cgroup_used_bytes=cgroup_used if pressure_fraction is not None else None,
        cgroup_limit_bytes=cgroup_total if pressure_fraction is not None else None,
        basis="cgroup" if pressure_fraction is not None else "server_rss_host",
        pressure_fraction=pressure_fraction,
    )


def _capacity_status(*, available: int | None, total: int | None) -> AdapterWarehouseHealthStatus:
    if available is None or total is None or total <= 0:
        return AdapterWarehouseHealthStatus.UNKNOWN
    available_fraction: float = available / total
    if available_fraction <= CLICKHOUSE_CAPACITY_CRITICAL_AVAILABLE_FRACTION:
        return AdapterWarehouseHealthStatus.CRITICAL
    if available_fraction <= CLICKHOUSE_CAPACITY_WARNING_AVAILABLE_FRACTION:
        return AdapterWarehouseHealthStatus.WARNING
    return AdapterWarehouseHealthStatus.HEALTHY


def _overall_status(
    *,
    disks: tuple[AdapterWarehouseDisk, ...],
    inode_status: AdapterWarehouseHealthStatus,
) -> AdapterWarehouseHealthStatus:
    disk_statuses: tuple[AdapterWarehouseHealthStatus, ...] = tuple(
        AdapterWarehouseHealthStatus(disk.status) for disk in disks
    )
    if all(status is AdapterWarehouseHealthStatus.UNKNOWN for status in disk_statuses):
        return AdapterWarehouseHealthStatus.UNKNOWN
    statuses: tuple[AdapterWarehouseHealthStatus, ...] = disk_statuses + (inode_status,)
    for candidate in (
        AdapterWarehouseHealthStatus.CRITICAL,
        AdapterWarehouseHealthStatus.WARNING,
        AdapterWarehouseHealthStatus.HEALTHY,
    ):
        if candidate in statuses:
            return candidate
    return AdapterWarehouseHealthStatus.UNKNOWN


def _unavailable(*, started_at: float) -> AdapterWarehouseHealth:
    return AdapterWarehouseHealth(
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
        tables=(),
        collection_duration_ms=_elapsed_ms(started_at),
        warnings=("Disk capacity is unavailable.",),
    )


def _elapsed_ms(started_at: float) -> int:
    return max(round((perf_counter() - started_at) * 1000), 0)
