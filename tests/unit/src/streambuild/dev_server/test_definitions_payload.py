from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.unit.src.streambuild.dev_server._test_types import DefinitionsFieldTestCase
from tests.unit.src.streambuild.dev_server.helpers import (
    build_test_client,
    named_payload_item,
    write_dev_server_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DefinitionsFieldTestCase(
            description="serializes model, source, and audit definitions",
            expected_model_name="orders_clean",
            expected_model_description="Cleaned order rows.",
            expected_column_description="Primary order id",
            expected_anchor="eligible",
            expected_audit_name="orders_clean.order_id.not_null.1",
            expected_audit_file_suffix="orders_clean.sql",
            expected_audit_generic_name="not_null",
            expected_driving_input="orders",
            expected_source_kind="kafka",
            expected_managed_ddl_fragment="CREATE",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_compiled_project_when_reading_definitions_then_serializes_expected_fields(
    test_case: DefinitionsFieldTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    client: TestClient = build_test_client(project_dir=tmp_path)

    payload: dict = client.get("/api/definitions").json()

    model: dict = named_payload_item(payload["models"], test_case.expected_model_name)
    assert model["description"] == test_case.expected_model_description
    assert model["drivingInput"] == test_case.expected_driving_input
    assert model["anchor"] == test_case.expected_anchor
    column: dict = named_payload_item(model["columns"], "order_id")
    assert column["description"] == test_case.expected_column_description
    assert model["sql"]["authored"].startswith("MODEL (")
    assert model["sql"]["compiled"]
    assert model["sql"]["ddl"]["table"]
    audit: dict = named_payload_item(payload["audits"], test_case.expected_audit_name)
    assert audit["file"].endswith(test_case.expected_audit_file_suffix)
    assert audit["genericName"] == test_case.expected_audit_generic_name
    source: dict = named_payload_item(payload["sources"], "orders")
    assert source["kind"] == test_case.expected_source_kind
    assert all(
        test_case.expected_managed_ddl_fragment in relation["ddl"]
        for relation in source["managedRelations"]
    )
    assert payload["project"]["database"] == "analytics"
