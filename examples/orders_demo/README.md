# Orders Demo

A runnable local `streambuild` demo using synthetic e-commerce order events.

- Redpanda for Kafka-compatible ingestion
- ClickHouse for storage and execution
- Fake producer generating order lifecycle events (no external API)

## Layout

- `docker/compose.yml`: Redpanda, Redpanda Console, and ClickHouse
- `producer/fake_orders_producer.py`: generates synthetic order events
- `streambuild_project.toml`: project defaults, target, and ClickHouse connection config
- `sources/order_events.yml`: managed Kafka source and replay boundary
- `pipelines/order_events/pipeline.yml`: pipeline source identity
- `pipelines/order_events/*.sql`: transform graph for orders, items, rollups

## Model DAG

```
source (order_events)
  |
  +-- orders (landing table, parse JSON)
  |     |
  |     +-- order_status_changes
  |     |     |
  |     |     +-- avg_fulfillment_time (SummingMergeTree)
  |     |
  |     +-- order_items
  |           |
  |           +-- daily_revenue (SummingMergeTree)
  |           |
  |           +-- hourly_order_volume (SummingMergeTree)
  |
  +-- order_cancellations (filtered: cancelled/refunded only)
        |
        +-- daily_cancellation_rates (SummingMergeTree)
```

## Start The Stack

```bash
docker compose -f examples/orders_demo/docker/compose.yml up -d --build
```

Services:

- Redpanda broker: `localhost:19092`
- Redpanda Console: `http://localhost:18081`
- ClickHouse HTTP: `localhost:18123`
- ClickHouse native: `localhost:19000`

## Run Streambuild

Plan:

```bash
uv run stb plan --project-dir examples/orders_demo
```

Backfill:

```bash
uv run stb backfill --project-dir examples/orders_demo
```

Audit:

```bash
uv run stb audit backfill --project-dir examples/orders_demo
```

Publish:

```bash
uv run stb publish --project-dir examples/orders_demo
```

## Producer Config

Environment variables:

- `KAFKA_BOOTSTRAP_SERVERS` default: `localhost:19092`
- `KAFKA_TOPIC` default: `source.order_events.live`
- `TICK_INTERVAL_SECONDS` default: `3`
- `NEW_ORDERS_PER_TICK` default: `2`
