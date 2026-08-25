import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from streambuild.adapter.models import (
    AdapterDirectFingerprintRecord,
    AdapterDirectFingerprintSnapshot,
    AdapterWarehouseActivity,
    AdapterWarehouseDisk,
    AdapterWarehouseHealth,
    AdapterWarehouseMemory,
    AdapterWarehouseTable,
)
from streambuild.compiler.compile.models import CompiledModel
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.classes.direct_model_fingerprint import DirectModelFingerprint
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.main._create_dev_app import create_dev_app
from tests.unit.src.streambuild.dev_server._test_types import (
    StateFieldTestCase,
    UnconfiguredFreshnessTestCase,
    ViewFreshnessTestCase,
    WarehouseHealthPayloadTestCase,
)
from tests.unit.src.streambuild.dev_server.helpers import (
    build_compile_callable,
    build_fake_state_connection,
    changed_storage_identity,
    write_dev_server_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StateFieldTestCase(
            description="unavailable baseline does not report drift",
            fingerprint_status="unavailable",
            definition_hash_builder=lambda model: DirectModelFingerprint.query_hash(model.query),
            identity_metadata_builder=lambda identity: json.dumps(
                identity,
                sort_keys=True,
                separators=(",", ":"),
            ),
            expected_source_freshness="fresh",
            expected_model_freshness="lagging",
            expected_model_lag_seconds=7200.0,
            expected_drift_reasons=(),
            expected_source_rows_per_second=0.083,
            expected_partition_max_offset=91822,
            expected_bucket_count=60,
        ),
        StateFieldTestCase(
            description="absent baseline reports missing fingerprint drift",
            fingerprint_status="absent",
            definition_hash_builder=lambda model: DirectModelFingerprint.query_hash(model.query),
            identity_metadata_builder=lambda identity: json.dumps(
                identity,
                sort_keys=True,
                separators=(",", ":"),
            ),
            expected_source_freshness="fresh",
            expected_model_freshness="lagging",
            expected_model_lag_seconds=7200.0,
            expected_drift_reasons=("missing",),
            expected_source_rows_per_second=0.083,
            expected_partition_max_offset=91822,
            expected_bucket_count=60,
        ),
        StateFieldTestCase(
            description="matching baseline does not report drift",
            fingerprint_status="available",
            definition_hash_builder=lambda model: DirectModelFingerprint.query_hash(model.query),
            identity_metadata_builder=lambda identity: json.dumps(
                identity,
                sort_keys=True,
                separators=(",", ":"),
            ),
            expected_source_freshness="fresh",
            expected_model_freshness="lagging",
            expected_model_lag_seconds=7200.0,
            expected_drift_reasons=(),
            expected_source_rows_per_second=0.083,
            expected_partition_max_offset=91822,
            expected_bucket_count=60,
        ),
        StateFieldTestCase(
            description="changed query reports query drift",
            fingerprint_status="available",
            definition_hash_builder=lambda _model: DirectModelFingerprint.query_hash(
                "previous query"
            ),
            identity_metadata_builder=lambda identity: json.dumps(
                identity,
                sort_keys=True,
                separators=(",", ":"),
            ),
            expected_source_freshness="fresh",
            expected_model_freshness="lagging",
            expected_model_lag_seconds=7200.0,
            expected_drift_reasons=("query",),
            expected_source_rows_per_second=0.083,
            expected_partition_max_offset=91822,
            expected_bucket_count=60,
        ),
        StateFieldTestCase(
            description="changed MODEL storage reports storage drift",
            fingerprint_status="available",
            definition_hash_builder=lambda model: DirectModelFingerprint.query_hash(model.query),
            identity_metadata_builder=changed_storage_identity,
            expected_source_freshness="fresh",
            expected_model_freshness="lagging",
            expected_model_lag_seconds=7200.0,
            expected_drift_reasons=("storage",),
            expected_source_rows_per_second=0.083,
            expected_partition_max_offset=91822,
            expected_bucket_count=60,
        ),
        StateFieldTestCase(
            description="baseline with null storage reports storage drift",
            fingerprint_status="available",
            definition_hash_builder=lambda model: DirectModelFingerprint.query_hash(model.query),
            identity_metadata_builder=lambda identity: json.dumps(
                {**identity, "storage": None},
                sort_keys=True,
                separators=(",", ":"),
            ),
            expected_source_freshness="fresh",
            expected_model_freshness="lagging",
            expected_model_lag_seconds=7200.0,
            expected_drift_reasons=("storage",),
            expected_source_rows_per_second=0.083,
            expected_partition_max_offset=91822,
            expected_bucket_count=60,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_warehouse_reads_when_reading_state_then_assembles_expected_overlay(
    test_case: StateFieldTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    analysis: CompileAnalysis = build_compile_callable(project_dir=tmp_path)()
    model: CompiledModel = analysis.compiled_project.models[0]
    desired_identity: dict[str, object] = DirectModelFingerprint.identity(
        model=model,
    )
    baseline: AdapterDirectFingerprintRecord = AdapterDirectFingerprintRecord(
        fingerprint_id="fingerprint",
        logical_model_identity=f"analytics.{model.key.name}",
        definition_sql=model.query,
        definition_hash=test_case.definition_hash_builder(model),
        identity_metadata=test_case.identity_metadata_builder(desired_identity),
        workflow_id="workflow",
        tool_version="test",
    )
    fingerprints: AdapterDirectFingerprintSnapshot = AdapterDirectFingerprintSnapshot(
        status=test_case.fingerprint_status,
        baselines=(baseline,),
    )
    client: TestClient = TestClient(
        create_dev_app(
            state=DevServerState(run_compile=build_compile_callable(project_dir=tmp_path)),
            connection=build_fake_state_connection(fingerprints=fingerprints),
            database="analytics",
            project_dir=tmp_path,
        )
    )

    response: Response = client.get("/api/state")
    payload: dict = response.json()

    assert response.status_code == 200
    assert set(payload) == {"capturedAt", "warehouseHealth", "models", "sources"}
    assert isinstance(payload["capturedAt"], str)
    assert payload["warehouseHealth"]["availability"] == "unavailable"
    assert payload["warehouseHealth"]["status"] == "unknown"
    assert payload["warehouseHealth"]["adapter"] == "clickhouse"
    assert payload["warehouseHealth"]["database"] == "analytics"
    assert set(payload["models"]) == {"orders_clean"}
    assert set(payload["sources"]) == {"orders"}
    model: dict = payload["models"]["orders_clean"]
    assert model["freshness"] == test_case.expected_model_freshness
    assert model["lagSeconds"] == test_case.expected_model_lag_seconds
    assert model["activity"]["state"] == "idle"
    assert model["activity"]["source"] == "system_parts"
    assert model["activity"]["approximate"] is True
    assert tuple(sorted(model["driftReasons"])) == test_case.expected_drift_reasons
    assert model["drift"] is bool(test_case.expected_drift_reasons)
    source: dict = payload["sources"]["orders"]
    assert source["freshness"] == test_case.expected_source_freshness
    assert source["lastArrivalSeconds"] == 2.0
    assert source["kafkaLagMessages"] is None
    assert source["rowsPerSecond"] == test_case.expected_source_rows_per_second
    assert source["partitions"][0]["maxOffset"] == test_case.expected_partition_max_offset
    assert len(source["throughput"]["buckets"]) == test_case.expected_bucket_count
    assert sum(source["throughput"]["buckets"]) == 300


@pytest.mark.parametrize(
    "test_case",
    [
        UnconfiguredFreshnessTestCase(
            description="missing policy leaves source and model freshness unconfigured",
            expected_source_freshness=None,
            expected_model_freshness=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_freshness_policy_when_reading_state_then_freshness_is_unconfigured(
    test_case: UnconfiguredFreshnessTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    source_path: Path = tmp_path / "sources" / "orders.yml"
    source_path.write_text(
        source_path.read_text(encoding="utf-8").replace(
            "    freshness:\n      warn_after: 1h\n      error_after: 4h\n",
            "",
        ),
        encoding="utf-8",
    )
    client: TestClient = TestClient(
        create_dev_app(
            state=DevServerState(run_compile=build_compile_callable(project_dir=tmp_path)),
            connection=build_fake_state_connection(),
            database="analytics",
            project_dir=tmp_path,
        )
    )

    response: Response = client.get("/api/state")
    payload: dict = response.json()

    assert response.status_code == 200
    assert payload["sources"]["orders"]["freshness"] == test_case.expected_source_freshness
    assert payload["models"]["orders_clean"]["freshness"] == test_case.expected_model_freshness


@pytest.mark.parametrize(
    "test_case",
    [
        ViewFreshnessTestCase(
            description="query-only view has no physical freshness measurements",
            expected_freshness=None,
            expected_lag_seconds=None,
            expected_newest_row_at=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_query_only_view_when_reading_state_then_physical_freshness_is_unmeasured(
    test_case: ViewFreshnessTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    (tmp_path / "pipelines" / "order_events" / "orders_summary.sql").write_text(
        "MODEL (\n  kind view,\n);\n\n"
        'SELECT order_id::String AS order_id FROM __ref("orders_clean")\n',
        encoding="utf-8",
    )
    client: TestClient = TestClient(
        create_dev_app(
            state=DevServerState(run_compile=build_compile_callable(project_dir=tmp_path)),
            connection=build_fake_state_connection(),
            database="analytics",
            project_dir=tmp_path,
        )
    )

    response: Response = client.get("/api/state")
    assert response.status_code == 200, response.text
    view: dict = response.json()["models"]["orders_summary"]
    assert view["freshness"] == test_case.expected_freshness
    assert view["lagSeconds"] == test_case.expected_lag_seconds
    assert view["newestRowAt"] == test_case.expected_newest_row_at


@pytest.mark.parametrize(
    "test_case",
    [
        WarehouseHealthPayloadTestCase(
            description="available diagnostics retain units labels and project table footprint",
            expected_status="warning",
            expected_disk_status="warning",
            expected_memory_basis="server_rss_host",
            expected_table_name="tbl__orders_clean",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_available_warehouse_health_when_reading_state_then_payload_is_truthful(
    test_case: WarehouseHealthPayloadTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    health: AdapterWarehouseHealth = AdapterWarehouseHealth(
        availability="available",
        status=test_case.expected_status,
        version="25.8.1.1",
        uptime_seconds=86400,
        disks=(
            AdapterWarehouseDisk(
                name="default",
                path="/data/clickhouse/",
                disk_type="Local",
                total_bytes=1000,
                free_bytes=160,
                unreserved_bytes=150,
                keep_free_bytes=10,
                status=test_case.expected_disk_status,
            ),
        ),
        inode_total=1000,
        inode_free=500,
        inode_status="healthy",
        memory=AdapterWarehouseMemory(
            resident_bytes=300,
            host_total_bytes=2000,
            cgroup_used_bytes=None,
            cgroup_limit_bytes=None,
            basis=test_case.expected_memory_basis,
            pressure_fraction=None,
        ),
        activity=AdapterWarehouseActivity(
            active_queries=2,
            active_merges=1,
            incomplete_mutations=0,
        ),
        tables=(
            AdapterWarehouseTable(
                name=test_case.expected_table_name,
                rows=900,
                bytes_on_disk=2048,
                active_parts=2,
            ),
        ),
        collection_duration_ms=4,
    )
    client: TestClient = TestClient(
        create_dev_app(
            state=DevServerState(run_compile=build_compile_callable(project_dir=tmp_path)),
            connection=build_fake_state_connection(warehouse_health=health),
            database="analytics",
            project_dir=tmp_path,
        )
    )

    response: Response = client.get("/api/state")
    payload: dict = response.json()["warehouseHealth"]

    assert response.status_code == 200
    assert payload["status"] == test_case.expected_status
    assert payload["database"] == "analytics"
    assert payload["disks"][0]["status"] == test_case.expected_disk_status
    assert payload["memory"]["basis"] == test_case.expected_memory_basis
    assert payload["memory"]["pressureFraction"] is None
    assert payload["tables"][0]["name"] == test_case.expected_table_name
    assert payload["activity"] == {
        "activeQueries": 2,
        "activeMerges": 1,
        "incompleteMutations": 0,
    }
