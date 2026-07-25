import json
from pathlib import Path

from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery._helpers.load import load_pipeline_file


def build_compiled_example_pipeline() -> CompiledPipeline:
    return compile_pipeline(
        load_pipeline_file(Path("tests/fixtures/basic_project/pipelines/orders/pipeline.yml"))
    )


def build_raw_orders_row() -> tuple[object, ...]:
    return (
        "order-1-key",
        json.dumps(
            {
                "order_id": "order-1",
                "customer_id": "customer-7",
                "order_total": 42.5,
                "created_at": "2026-04-05 12:00:00.123",
                "updated_at": "2026-04-05 12:01:00.456",
            }
        ),
        "source.orders.created",
        0,
        1,
        "2026-04-05 12:00:00.123",
        0,
        1,
        "2026-04-05 12:00:00.123",
        "",
        "2026-04-05 12:00:00.789",
        "2026-04-05 12:00:00.789",
    )
