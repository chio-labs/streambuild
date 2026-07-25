# streambuild

Declarative ClickHouse streaming pipeline deployment for staged backfill, audit, and publish workflows.

`streambuild` is aimed at streaming data teams who want dbt-like authored models, but with deployment semantics that fit live ClickHouse pipelines:

- plan rebuilds conservatively
- create staged shadow objects
- backfill history into the staged path
- audit staged readiness
- publish by switching stable logical views

The current product is centered on ClickHouse and streaming replay semantics. Kafka-backed sources work today, and adopted external streaming tables are now supported as replay roots.

## Current Status

Current implemented workflow:

- `stb plan`
- `stb backfill`
- `stb audit backfill`
- `stb publish`
- `stb doctor`
- `stb repair active-view`
- `stb reconcile`
- `stb compile`
- `stb janitor`

Current rollout model:

- `plan` is read-only
- `backfill` starts a real staged deployment
- `audit backfill` inspects staged readiness
- `publish` switches stable logical views to staged physical tables

## Installation

Requirements:

- Python `>=3.14`
- ClickHouse

Local dev install:

```bash
uv sync
```

Run the CLI with:

```bash
uv run stb --help
```

## Project Shape

StreamBuild projects are authored as a project root plus pipeline folders.

```text
streambuild_project.yml
pipelines/
  orders/
    pipeline.yml
    orders_enriched.sql
    order_rollups.sql
```

Rules:

- each pipeline folder contains one `pipeline.yml`
- recursive `*.sql` files under that folder belong to that pipeline
- pipeline name is inferred from the folder name
- model name is inferred from the SQL filename stem

## Project Config

Project-wide defaults live in `streambuild_project.yml`.

```yaml
default_database: analytics
replay_lineage_mode: offsets

clickhouse:
  host: localhost
  port: 8123
  username: clickhouse
  password: clickhouse
```

Notes:

- `default_database` is the user-facing database setting
- metadata lives in the same database by default
- CLI flags override environment variables, and environment variables override `streambuild_project.yml`

## Pipeline Sources

`pipeline.yml` defines the replay-driving source for a pipeline.

### Managed Kafka Landing

```yaml
source:
  kind: kafka
  name: orders
  broker_list: kafka:9092
  topic: source.orders.created
```

This is the managed source shape:

- StreamBuild creates the Kafka table
- StreamBuild creates the raw landing table and landing MV
- downstream models usually read the source via `__source("orders")`

### Adopted External Source

```yaml
source:
  kind: kafka
  name: orders
  table_name: orders_existing
  replay_boundary:
    mode: offsets
    columns:
      _replay_partition: event_partition
      _replay_offset: event_offset
      _replay_timestamp: event_timestamp
```

This is the adopted-source shape:

- StreamBuild does not create the source table
- the source table must already exist in the resolved project database
- `table_name` must currently be a bare table name
- replay boundary columns are validated against the live table schema during planning/runtime commands

Current replay-boundary rules for adopted sources:

- `mode: offsets` requires `partition`, `offset`, and `timestamp`
- `mode: offsets` does not allow `landed_at`
- `mode: timestamp` requires `timestamp`
- `mode: timestamp` does not allow `landed_at`
- `mode: cursor` requires `cursor` and `timestamp`

Currently supported external-source replay boundary modes:

- `offsets`
- `timestamp`

- `cursor`

## Models

Each SQL model starts with a `MODEL (...)` header.

```sql
MODEL ();

SELECT
  CAST(order_id AS UInt64) AS order_id
FROM __source("orders")
```

Notes:

- the driving replay input may be declared with `__source(...)` for source roots or `__ref(...)` for managed upstream models
- additional managed dependencies are declared with `__ref(...)`
- additional `__ref(...)` dependencies must declare `ref_type`
- omitted SQL storage settings default to `engine: "MergeTree()"` and `order_by: ["_replay_timestamp"]`
- both `CAST(expr AS Type)` and `expr::Type` are accepted

## Replay Lineage

StreamBuild exposes a normalized replay lineage surface.

Current intent:

- `replay_*` is the normalized source-agnostic replay vocabulary

Current generic replay columns:

- `_replay_partition`
- `_replay_offset`
- `_replay_timestamp`
- `_replay_landed_at`
- `_replay_cursor`

Current behavior:

- managed Kafka landing populates the normalized `replay_*` lineage columns directly
- adopted sources map declared physical source columns into the normalized replay surface
- downstream managed outputs should preserve `replay_*` when they need replay lineage

## Core Commands

From a project directory:

```bash
uv run stb plan
uv run stb backfill
uv run stb audit backfill
uv run stb publish
uv run stb doctor
uv run stb repair active-view --table tbl__orders
uv run stb reconcile
uv run stb compile
uv run stb janitor
```

From outside the project directory:

```bash
uv run stb plan --project-dir examples/orders_demo
```

## Compile Artifacts

`stb compile` writes artifacts under project-level `target/`.

Current layout:

```text
target/
  manifest.json
  <pipeline>/
    compile/
      models/
    run/
      models/
      workflow/
```

The compile manifest includes:

- resolved database
- relations
- source metadata
- model specs
- artifact paths
- workflow paths

## Example

See `examples/orders_demo/` for a runnable local demo using:

- Redpanda
- ClickHouse
- a synthetic producer
- a real `streambuild` project

Demo README:

- `examples/orders_demo/README.md`

## Development

Useful commands:

```bash
make format
make lint
make type
make test
make test-all
make check
make verify
```

Current meanings:

- `make check`: fast structural and static validation
- `make verify`: full validation including tests

## Testing

The repo uses:

- unit tests under `tests/unit`
- integration tests under `tests/integration`
- end-to-end tests under `tests/e2e`

Recent coverage includes:

- staged backfill / audit / publish flows
- active-view diagnosis and repair
- adopted external replay sources
- normalized replay lineage behavior

## Scope Notes

Current intentional limitations:

- ClickHouse-only runtime
- external adopted sources must resolve in the project database
- `cursor` replay mode is not implemented yet

This repo is actively evolving around staged rollout correctness, replay semantics, and migration/adoption support for existing ClickHouse streaming tables.
