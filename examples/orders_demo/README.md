# Commerce Events Demo

A local StreamBuild V2 demo built around one fixed commerce-event contract. Redpanda retains the
events, ClickHouse serves the pipeline, and the bundled producer has no external dependencies or
network side effects beyond the local Kafka broker.

Every producer message has the same keys and stable types:

```text
event_id, event_type, schema_version, order_id, customer_id, product, category,
quantity, unit_price_cents, currency, status, region_code, event_at
```

Quantities and prices are JSON numbers. Prices stay in integer cents through storage and
aggregation. The regular producer uses monotonic deterministic IDs and a durable pending-event
checkpoint; the one-shot injector uses a separate unique namespace. Producer state is stored in a
disposable Compose volume so a restart continues in-flight order lifecycles.

## Pipeline

```text
commerce_event_stream source
  -> commerce_events (typed envelope, 7-day TTL)
       -> order_events (validated lifecycle with deterministic region labels)
            -> order_event_facts (append-only additive rows)
                 -> commerce_kpis (terminal view deduplicating replay before deriving KPIs)
```

Region labels are rendered by the same tested macro used in production SQL, avoiding a mutable side
table in the primary ingestion path. The terminal view explicitly keeps the highest replay offset
for each event before deriving non-additive values from the append-only facts. Kafka retention and
event models are bounded to seven days after landing. Source freshness warns after 30 seconds and
errors after two minutes.

## Workflow

Prerequisites: Docker with Compose, Node.js 20.19 or newer, npm, and the repository's `stb`
environment with generated UI assets installed:

```bash
make ui-install ui-build
uv tool install --editable .
cd examples/orders_demo
cp .env.example .env
make start
```

`make start` builds the producer image, waits for healthy Redpanda and ClickHouse services, creates
`source.order_events.live` with three partitions, starts the producer, and applies the StreamBuild
project. The Compose project identity defaults to `streambuild-orders-demo`; every published port is
bound to `127.0.0.1`. The shared `redpanda.localhost:19092` broker name resolves to loopback for
host-side Topics and lag reads and to the Redpanda container for ClickHouse ingestion.

Services:

- Redpanda broker: `localhost:19092`
- Redpanda Console: `http://localhost:18081`
- ClickHouse HTTP: `localhost:18123`
- ClickHouse native: `localhost:19000`

Use the local UI and scheduler in one terminal:

```bash
make dev
```

Run the focused SQL tests independently:

```bash
stb test --project-dir .
```

With `make dev` still running, verify the topic contract, logical event cardinality, region labels,
model drift, view freshness, Kafka lag, all four SQL tests, and every audit:

```bash
make verify
make verify-warning
```

`make verify-warning` takes about 30 seconds and exercises the sampled warning, natural recovery,
and both sensor deliveries end to end.

Reset all disposable broker and warehouse data, or stop while retaining it:

```bash
make reset
make stop
```

## Warning And Recovery

The `no_future_events` warning audit has a ten-second cadence. Its running sensor uses the honest
`ConsoleNotifier` provider: it prints locally and never sends a webhook.

With `make dev` running, inject one order 30 seconds into the future from another terminal:

```bash
make inject
```

The console first prints a `WARNING` transition with one sample and an exact Quality link. Once the
clock is within two seconds of the event timestamp, the same persisted row stops violating the audit
and the console prints `RECOVERED`. Change
`FUTURE_EVENT_SECONDS` in `.env` to adjust that bounded demonstration window.

## Direct Commands

The Make targets are wrappers around these project operations:

```bash
stb compile --project-dir .
stb plan --project-dir .
stb build --project-dir .
stb audit --project-dir .
```

The project intentionally uses direct mode so a first run has no deployment or promotion step.
