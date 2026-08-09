<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/streambuild/main/.github/streambuild-logo-dark.png" alt="StreamBuild" width="100%">
</p>

<p align="center">
  Declarative ClickHouse streaming pipelines with replay-aware builds and staged deployments.
</p>

StreamBuild compiles typed SQL models into ClickHouse tables and materialized views, plans the
affected graph, and rebuilds it from retained streaming history.

- **Direct mode** rebuilds selected live relations immediately.
- **Virtual mode** builds deployment-specific relations for review, audit, promotion, and rollback.
- **Mixed mode** stages virtual pipelines before applying direct pipelines in one invocation.

StreamBuild currently targets ClickHouse. It supports managed Kafka landing and adopted external
stream tables.

## Install

Requires Python 3.12 or newer.

```bash
pip install streambuild
stb --help
```

For repository development:

```bash
uv sync
uv run stb --help
```

## Project

```text
streambuild_project.toml
sources/
  orders.yml
macros/
  common.py
pipelines/
  orders/
    pipeline.toml
    order_totals.sql
audits/
tests/
```

Each direct child of `pipelines/` is a pipeline. SQL filenames define logical model names, and
StreamBuild infers pipeline sources by following `__source()` and `__ref()` dependencies.

Minimal configuration:

```toml
name = "orders"
default_target = "dev"

[connection]
host = "localhost"
port = 8123
username = "default"
password = "${ENV:CLICKHOUSE_PASSWORD}"

[defaults]
pipeline_mode = "direct"
run_presumed_failed_after = "10m"

[targets.dev]
database = "analytics"
```

Developer-specific target and connection overrides belong in the gitignored
`streambuild_local.toml`.

## Sources

Managed Kafka source:

```yaml
sources:
  - name: orders
    kind: kafka
    broker_list: kafka:9092
    topic: source.orders
    replay_boundary:
      mode: offsets
```

Adopted ClickHouse source:

```yaml
sources:
  - name: orders
    kind: stream_table
    table_name: orders_existing
    replay_boundary:
      mode: offsets
      columns:
        _replay_partition: event_partition
        _replay_offset: event_offset
        _replay_timestamp: event_time
```

StreamBuild owns managed Kafka landing objects. It validates but never mutates adopted source
tables.

## Models

```sql
MODEL (
  engine "MergeTree()",
  order_by ["order_id", "_replay_partition", "_replay_offset"],
);

SELECT
  order_id::String AS order_id,
  _replay_partition::Int32 AS _replay_partition,
  _replay_offset::Int64 AS _replay_offset,
  _replay_timestamp::DateTime64(3) AS _replay_timestamp
FROM __source("orders")
```

Models must project explicit output types. Table models preserve replay lineage through normalized
`_replay_*` columns. Terminal query views use `MODEL (kind view)`.

Python functions under `macros/` are available in model, test, and audit SQL as `@function_name()`.

## Workflow

```bash
stb discover                 # inspect authored resources
stb compile                  # offline validation and artifacts
stb plan                     # read-only warehouse plan
stb build                    # confirm and execute
stb test
stb audit
stb dev                      # local UI at 127.0.0.1:8000
```

Select a model or pipeline with repeatable selectors:

```bash
stb plan --select pipeline:orders
stb build --select order_totals --start-time 2026-08-01T00:00:00Z
```

Protected pipelines require their exact configured `--confirm` value even with
`--auto-approve`.

## Deployments

Set `pipeline_mode = "virtual"` project-wide or `mode = "virtual"` in `pipeline.toml`.

```bash
stb build
stb deployment list
stb deployment show <deployment-id>
stb deployment diff <deployment-id>
stb deployment audit <deployment-id>
stb deployment promote <deployment-id>
stb deployment rollback --previous
```

Promotion and rollback switch stable views one relation at a time. Rollback restores a retained
publication's bindings, not a historical data snapshot.

## Development UI

`stb dev` serves one resolved project and target. The UI provides:

- overview, lineage, pipeline, catalog, source, topic, and message inspection
- connected plan previews and protected-pipeline confirmation
- direct, virtual, and mixed build execution
- deployment inventory, diff, promotion, and cleanup
- durable run timelines, statement progress, cancellation, and stale-run recovery guidance
- audit history and scheduler health

Run observability is warehouse-backed. A silent run becomes `unresponsive` after 45 seconds and
`presumed_failed` after `[defaults].run_presumed_failed_after` (default `10m`). A new build is blocked
until that safety window expires to prevent overlapping warehouse writes.

## Guarantees

- `stb compile` is connection-free and writes disposable artifacts under `target/`.
- `stb plan` is read-only; `stb build` always replans against current warehouse state.
- Lifecycle state is append-only metadata in the selected target database.
- Failed or cancelled builds are rerun, never resumed from copied SQL artifacts.
- Workflow statements execute serially to avoid unbounded ClickHouse memory pressure.

## Documentation

- [Documentation source](https://github.com/chio-labs/streambuild-docs)
- [Runnable orders demo](examples/orders_demo/README.md)
- [Changelog](CHANGELOG.md)

## Development

```bash
make check-ci
make test
make test-all
make ui-build
```

Tests are split across `tests/unit`, `tests/integration`, and `tests/e2e`.
