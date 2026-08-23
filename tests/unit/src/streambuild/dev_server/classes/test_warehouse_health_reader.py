from typing import cast
from unittest.mock import MagicMock

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterWarehouseDisk, AdapterWarehouseHealth
from streambuild.dev_server.classes.warehouse_health_reader import WarehouseHealthReader
from tests.unit.src.streambuild.dev_server.classes._test_types import (
    WarehouseHealthRetentionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        WarehouseHealthRetentionTestCase(
            description="failed refresh retains prior evidence and marks it stale",
            expected_availability="partial",
            expected_status="healthy",
            expected_stale=True,
            expected_warning="Warehouse diagnostics are unavailable.",
            first_measured_at="2026-08-23 10:00:00.000",
            second_measured_at="2026-08-23 10:00:15.000",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_usable_health_then_failed_refresh_when_reading_then_prior_evidence_is_stale(
    test_case: WarehouseHealthRetentionTestCase,
) -> None:
    usable: AdapterWarehouseHealth = AdapterWarehouseHealth(
        availability="available",
        status="healthy",
        version="25.8.1.1",
        uptime_seconds=100,
        disks=(
            AdapterWarehouseDisk(
                name="default",
                path="/data/",
                disk_type="Local",
                total_bytes=100,
                free_bytes=50,
                unreserved_bytes=50,
                keep_free_bytes=0,
                status="healthy",
            ),
        ),
        inode_total=100,
        inode_free=50,
        inode_status="healthy",
        memory=None,
        activity=None,
        tables=(),
        collection_duration_ms=2,
    )
    connection: MagicMock = MagicMock(spec=AdapterConnection)
    connection.load_warehouse_health.side_effect = [
        usable,
        RuntimeError("provider detail must not escape"),
    ]
    reader: WarehouseHealthReader = WarehouseHealthReader()

    first: AdapterWarehouseHealth = reader.read(
        connection=cast(AdapterConnection, connection),
        database="analytics",
        measured_at=test_case.first_measured_at,
    )
    second: AdapterWarehouseHealth = reader.read(
        connection=cast(AdapterConnection, connection),
        database="analytics",
        measured_at=test_case.second_measured_at,
    )

    assert first.measured_at == test_case.first_measured_at
    assert str(second.availability) == test_case.expected_availability
    assert str(second.status) == test_case.expected_status
    assert second.stale is test_case.expected_stale
    assert second.disks == usable.disks
    assert second.warnings == (test_case.expected_warning,)
    assert second.measured_at == test_case.first_measured_at
