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
- `pipelines/pl__order_events/`: models for the order transform graph

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

Build:

```bash
uv run stb build --project-dir examples/orders_demo
```

The demo uses `pipeline_mode = "direct"`, so the build applies immediately. Open the development UI:

```bash
uv run stb dev --project-dir examples/orders_demo
```

The UI shows the model graph, live catalog state, source throughput and lag, runs, quality checks,
Kafka topics, and retained source messages.

To try staged deployment commands, change `[defaults].pipeline_mode` to `"virtual"`, build again,
then list and inspect deployments:

```bash
uv run stb deployment list --project-dir examples/orders_demo
uv run stb deployment show <deployment-id> --project-dir examples/orders_demo
uv run stb deployment diff <deployment-id> --project-dir examples/orders_demo
```

Audit a staged deployment:

```bash
uv run stb deployment audit <deployment-id> --project-dir examples/orders_demo
```

Promote:

```bash
uv run stb deployment promote <deployment-id> --project-dir examples/orders_demo
```

After publishing another deployment, compare it with the active graph or roll the complete graph
back to the preceding publication:

```bash
uv run stb deployment diff <from-id>:<to-id> --project-dir examples/orders_demo
uv run stb deployment rollback --previous --project-dir examples/orders_demo
```

Rollback rebinds retained live deployment tables; it does not restore a historical data snapshot.

## Producer Config

Environment variables:

- `KAFKA_BOOTSTRAP_SERVERS` default: `localhost:19092`
- `KAFKA_TOPIC` default: `source.order_events.live`
- `TICK_INTERVAL_SECONDS` default: `3`
- `NEW_ORDERS_PER_TICK` default: `2`
