from streambuild.compiler.discovery.models import TransformStep


def build_transform() -> TransformStep:
    return TransformStep(
        name="orders_enriched",
        source="orders",
        engine="ReplacingMergeTree(updated_at)",
        order_by=["order_id", "updated_at"],
        partition_by="toYYYYMM(created_at)",
        ttl="toDateTime(created_at) + INTERVAL 30 DAY",
        settings={"index_granularity": "8192"},
        query="""
            SELECT
                CAST(order_id AS String) AS order_id,
                CAST(updated_at AS DateTime64(3)) AS updated_at,
                CAST(now64(3) AS DateTime64(3)) AS _replay_landed_at
            FROM __ref("orders")
        """,
    )
