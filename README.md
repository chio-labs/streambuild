<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/streambuild/main/.github/streambuild-logo-dark.png" alt="StreamBuild" width="100%">
</p>

<p align="center">
  Declarative ClickHouse streaming pipeline deployment for staged backfill, audit, and publish workflows.
</p>

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
- `stb build`
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

- Python `>=3.12`
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
streambuild_project.toml
sources/
  orders.yml
macros/
  common.py
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

## Macros

Public Python modules under `macros/` are loaded once per project analysis. Functions
defined by those modules are available in authored model, test, and audit SQL as
`@function_name(...)`. Imported functions, async functions, `__init__.py`, and modules
or directories whose names start with `_` are not registered.

```python
from streambuild.compiler.macros.models import MacroContext


def qualified_source(ctx: MacroContext, table_name: str) -> str:
    return f"{ctx.database}.{table_name}"
```

```sql
SELECT * FROM @qualified_source("orders")
```

Macro modules are trusted project code, not a sandbox: module-level code runs during
analysis, and a macro may perform anything allowed to that Python process. Calls accept
only nested Python literals (`str`, `bool`, `int`, `float`, `None`, lists, tuples, and
dictionaries with scalar keys) plus nested macro results. A first parameter named `ctx`
must be annotated as `MacroContext`; StreamBuild supplies its immutable project target,
adapter, database, virtual-environment, and variable values. Direct SQL macro calls must
return strings. Errors report both the authored SQL call and the defining macro source.

## Project Config

Committed project configuration lives in `streambuild_project.toml`. Developer-specific
overrides may live in the gitignored `streambuild_local.toml`.

```toml
name = "orders_project"
default_target = "dev"

[settings]
virtual_environments = true

[connection]
host = "localhost"
port = 8123
username = "clickhouse"
password = "${ENV:CLICKHOUSE_PASSWORD}"

[targets.dev]
database = "analytics"
```

Notes:

- `name` and `default_target` are required; `adapter` defaults to `clickhouse`
- target selection is CLI `--target`, local `target`, then project `default_target`
- CLI `--vars` accepts one JSON object for `${name}` interpolation
- connection templates are expanded only for commands that connect
- metadata lives in the same database by default
- connection precedence is CLI flags, fixed `STREAMBUILD_CLICKHOUSE_*` environment
  variables, local config, selected target, then project config

## Pipeline Sources

Reusable replay-driving sources live under `sources/*.yml`. Each `pipeline.yml` contains
one source registry identity, for example `source: orders`.

### Managed Kafka Landing

```yaml
sources:
  - kind: kafka
    name: orders
    broker_list: kafka:9092
    topic: source.orders.created
    replay_boundary:
      mode: offsets
```

This is the managed source shape:

- StreamBuild creates the Kafka table
- StreamBuild creates the raw landing table and landing MV
- downstream models usually read the source via `__source("orders")`

### Adopted External Source

```yaml
sources:
  - kind: stream_table
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

Virtual-environment projects can choose change-driven replay independently from the
fallback used when bounded replay cannot preserve aggregate history:

```yaml
source: orders
replay_on_change:
  breaking: full
  non_breaking: bounded-7d
bounded_replay_fallback: bounded_without_history
```

The same policies can be defaults in `streambuild_project.toml` and overrides in a model
`MODEL(...)` header. They are rejected when `settings.virtual_environments` is false.

## Models

Each SQL model starts with a `MODEL (...)` header.

```sql
MODEL (
  engine "MergeTree()",
  order_by ["order_id", "_replay_partition", "_replay_offset"],
  partition_by "toYYYYMM(event_at)",
  ttl "event_at + INTERVAL 30 DAY",
  settings (
    index_granularity 8192,
  ),
  replay_anchor auto,
);

SELECT
  CAST(order_id AS UInt64) AS order_id,
  CAST(event_at AS DateTime64(3)) AS event_at,
  CAST(_replay_partition AS Int32) AS _replay_partition,
  CAST(_replay_offset AS Int64) AS _replay_offset
FROM __source("orders")
```

Notes:

- the driving replay input may be declared with `__source(...)` for source roots or `__ref(...)` for managed upstream models
- additional managed dependencies are declared with `__ref(...)`
- additional `__ref(...)` dependencies must declare `ref_type`
- header fields use SQLBuild syntax: whitespace-separated `key value` entries, lists in `[...]`, and nested mappings in `(...)`
- omitted SQL storage settings default to `engine "MergeTree()"` and `order_by ["_replay_timestamp"]`
- both `CAST(expr AS Type)` and `expr::Type` are accepted

## Replay Lineage

StreamBuild exposes a normalized replay lineage surface.

Current intent:

- `_replay_*` is the normalized source-agnostic replay vocabulary

Current generic replay columns:

- `_replay_partition`
- `_replay_offset`
- `_replay_timestamp`
- `_replay_landed_at`
- `_replay_cursor`

Current behavior:

- managed Kafka landing populates the normalized `_replay_*` lineage columns directly
- adopted sources map declared physical source columns into the normalized replay surface
- downstream managed outputs should preserve `_replay_*` when they need replay lineage

## Core Commands

From a project directory:

```bash
uv run stb plan
uv run stb build
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

Static compile products and runtime evidence have separate owners:

```text
target/
  manifest.json
  streambuild_dag.json
  compiled/
    models/<pipeline>/
    resources/
      sources/<source>/
      models/<pipeline>/
    workflows/<pipeline>/
      steps/
      workflow.sql
      workflow.json
    audits/
    tests/
  run/
    tests/
```

`stb compile` atomically replaces only the static owners and never writes under
`target/run/`. Runtime commands own their command-specific subtrees.

The compile manifest includes:

- resolved database
- relations
- source metadata
- model specs
- logical tests and audits
- realized adapter resources
- every emitted static artifact path
- workflow paths and logical DAG identity

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
- managed Kafka sources support `offsets`, `timestamp`, and `landed_at`; adopted relations
  support `offsets`, `timestamp`, and `cursor`

This repo is actively evolving around staged rollout correctness, replay semantics, and migration/adoption support for existing ClickHouse streaming tables.
