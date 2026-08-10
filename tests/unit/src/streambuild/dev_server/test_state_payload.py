import json
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from streambuild.adapter.models import (
    AdapterDirectFingerprintRecord,
    AdapterDirectFingerprintSnapshot,
)
from streambuild.compiler.compile.main.build_model_storage_identity import (
    build_model_storage_identity,
)
from streambuild.compiler.compile.models import CompiledModel
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.main._create_dev_app import create_dev_app
from tests.unit.src.streambuild.dev_server._test_types import StateFieldTestCase
from tests.unit.src.streambuild.dev_server.helpers import (
    build_compile_callable,
    build_fake_state_connection,
    write_dev_server_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StateFieldTestCase(
            description="unavailable baseline does not report drift",
            fingerprint_status="unavailable",
            definition_hash_builder=lambda model: sha256(model.query.encode()).hexdigest(),
            identity_metadata_builder=lambda model: json.dumps(
                {"storage": build_model_storage_identity(model)},
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
            description="matching baseline does not report drift",
            fingerprint_status="available",
            definition_hash_builder=lambda model: sha256(model.query.encode()).hexdigest(),
            identity_metadata_builder=lambda model: json.dumps(
                {"storage": build_model_storage_identity(model)},
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
            definition_hash_builder=lambda _model: sha256(b"previous query").hexdigest(),
            identity_metadata_builder=lambda model: json.dumps(
                {"storage": build_model_storage_identity(model)},
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
            definition_hash_builder=lambda model: sha256(model.query.encode()).hexdigest(),
            identity_metadata_builder=lambda model: json.dumps(
                {
                    "storage": {
                        **(build_model_storage_identity(model) or {}),
                        "ttl": "created_at + INTERVAL 1 DAY",
                    }
                },
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
        StateFieldTestCase(
            description="baseline without storage reports storage drift",
            fingerprint_status="available",
            definition_hash_builder=lambda model: sha256(model.query.encode()).hexdigest(),
            identity_metadata_builder=lambda _model: "{}",
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
    baseline: AdapterDirectFingerprintRecord = AdapterDirectFingerprintRecord(
        fingerprint_id="fingerprint",
        logical_model_identity=f"analytics.{model.key.name}",
        definition_sql=model.query,
        definition_hash=test_case.definition_hash_builder(model),
        identity_metadata=test_case.identity_metadata_builder(model),
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
    assert set(payload) == {"capturedAt", "models", "sources"}
    assert isinstance(payload["capturedAt"], str)
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
