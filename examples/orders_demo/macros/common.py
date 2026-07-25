"""Common macros for the orders demo pipeline."""


def replay_columns() -> str:
    """Generate the standard replay lineage columns."""
    return (
        "_replay_partition::Int64 AS _replay_partition,\n"
        "  _replay_offset::Int64 AS _replay_offset,\n"
        "  _replay_timestamp::DateTime64(3) AS _replay_timestamp,\n"
        "  _replay_landed_at::DateTime64(3) AS _replay_landed_at"
    )


def mock_rows(rows: list[dict]) -> str:
    """Generate UNION ALL from a list of dicts."""
    selects: list[str] = []
    for row in rows:
        cols: str = ", ".join(
            f"'{v}' AS {k}"
            if isinstance(v, str)
            else f"NULL AS {k}"
            if v is None
            else f"{v} AS {k}"
            for k, v in row.items()
        )
        selects.append(f"SELECT {cols}")
    return "\n  UNION ALL\n  ".join(selects)


def timestamp_literal(ts: str) -> str:
    """Generate a DateTime64 literal."""
    return f"toDateTime64('{ts}', 3)"


def load_fixture(name: str) -> list[dict]:
    """Return fixture data by name (for nested macro testing)."""
    fixtures: dict[str, list[dict]] = {
        "orders_simple": [
            {
                "order_id": "ord_001",
                "customer_id": "cust_001",
                "product": "Widget",
                "category": "electronics",
                "quantity": 2,
                "unit_price": 10.0,
                "status": "created",
                "region": "us-east",
                "event_at": "2026-04-19 10:00:00",
            },
            {
                "order_id": "ord_002",
                "customer_id": "cust_002",
                "product": "Gadget",
                "category": "clothing",
                "quantity": 3,
                "unit_price": 5.0,
                "status": "paid",
                "region": "eu-west",
                "event_at": "2026-04-19 11:00:00",
            },
        ],
        "orders_with_nulls": [
            {
                "order_id": "ord_001",
                "customer_id": "cust_001",
                "product": "Widget",
                "category": "electronics",
                "quantity": None,
                "unit_price": 10.0,
                "status": "created",
                "region": "us-east",
                "event_at": "2026-04-19 10:00:00",
            },
            {
                "order_id": "ord_002",
                "customer_id": "cust_002",
                "product": "Gadget",
                "category": "clothing",
                "quantity": 3,
                "unit_price": None,
                "status": "paid",
                "region": "eu-west",
                "event_at": "2026-04-19 11:00:00",
            },
        ],
    }
    if name not in fixtures:
        raise ValueError(f"Unknown fixture: {name}. Available: {list(fixtures.keys())}")
    return fixtures[name]


def with_timestamps(rows: list[dict], ts: str) -> list[dict]:
    """Add replay timestamp columns to each row in a fixture."""
    result: list[dict] = []
    for i, row in enumerate(rows):
        enriched: dict = {
            **row,
            "_replay_partition": 0,
            "_replay_offset": i + 1,
            "_replay_timestamp": ts,
            "_replay_landed_at": ts,
        }
        result.append(enriched)
    return result
