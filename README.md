<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/streambuild/main/.github/streambuild-logo-dark.png" alt="StreamBuild" width="100%">
</p>

<p align="center">
  Declarative SQL streaming pipelines for ClickHouse, with replay-aware builds and staged deployments.
</p>

<p align="center">
  <a href="https://pypi.org/project/streambuild/"><img src="https://img.shields.io/pypi/v/streambuild" alt="PyPI"></a>
  <a href="https://github.com/chio-labs/streambuild/actions/workflows/verify.yml"><img src="https://github.com/chio-labs/streambuild/actions/workflows/verify.yml/badge.svg" alt="Verification"></a>
  <a href="https://pypi.org/project/streambuild/"><img src="https://img.shields.io/pypi/pyversions/streambuild" alt="Python versions"></a>
  <a href="https://github.com/chio-labs/streambuild/blob/main/LICENSE"><img src="https://img.shields.io/github/license/chio-labs/streambuild" alt="License"></a>
</p>

StreamBuild lets data teams define continuously updating ClickHouse pipelines in typed SQL, inspect
the affected graph before making changes, and rebuild it from retained streaming history when logic
changes.

It brings dbt-style authoring and deployment workflows to streaming workloads:

- **Declarative models** compile into ClickHouse tables and materialized views.
- **Replay-aware builds** reconstruct affected models from retained stream history.
- **Safe planning** shows the graph and warehouse operations before execution.
- **Staged deployments** support review, audit, promotion, and graph-level rollback.
- **Built-in observability** covers sources, lag, lineage, runs, quality checks, and sensors.

StreamBuild currently targets ClickHouse and supports managed Kafka landing or adopted external
stream tables.

## Install

Requires Python 3.12 or newer.

```bash
pip install streambuild
stb --help
```

## Quickstart

The included deterministic commerce demo runs locally with Redpanda and ClickHouse. It requires
Docker with Compose, Node.js 20.19 or newer, npm, and [`uv`](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/chio-labs/streambuild.git
cd streambuild
make ui-install ui-build
uv tool install --editable .

cd examples/orders_demo
cp .env.example .env
make start
make dev
```

Open `http://127.0.0.1:8000` to inspect three Kafka partitions, retained messages, replay-safe model
facts, tests, audits, and Kafka lag. See the [commerce events demo](examples/orders_demo/README.md)
for its fixed event contract and controlled warning/recovery walkthrough.

## How it works

```text
Kafka or an adopted stream table
              |
              v
      retained landing data
              |
              v
 typed SQL models -> ClickHouse tables and materialized views
              |
              v
 plan -> build or stage -> audit -> promote
```

StreamBuild follows `__source()` and `__ref()` dependencies to compile the model graph. Live
materialized views keep it current; retained replay columns let a later build reconstruct the
affected scope after SQL changes.

## Project

```text
streambuild_project.toml
sources/
  orders.yml
macros/
  common.py
pipelines/
  pl__orders/
    pipeline.toml
    order_totals.sql
audits/
tests/
```

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

StreamBuild owns managed Kafka landing objects. It validates but never mutates adopted source
tables. See the [pipeline documentation](https://docs.streambuild.dev/concepts/pipelines)
for adopted stream-table configuration.

## Pipelines

Each direct child of `pipelines/` is a pipeline. Its directory name is its logical name:

```text
pipelines/
  pl__orders/
    staging/
      orders_clean.sql
    order_totals.sql
```

Nested directories organize models but do not change pipeline identity. Pipeline, source, and model
names share one namespace and must be unique.

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
stb plan --select pipeline:pl__orders
stb build --select order_totals --start-time 2026-08-01T00:00:00Z
```

`stb compile` is offline. `stb plan` reads warehouse state but cannot mutate it. `stb build` replans
immediately before execution so an approved command never relies on a stale plan.

## Build modes

| Mode | Behavior | Best for |
| --- | --- | --- |
| **Direct** | Rebuilds selected live relations immediately | Development and explicitly controlled live changes |
| **Virtual** | Builds deployment-specific relations before promotion | Review, validation, and production releases |
| **Mixed** | Stages virtual pipelines before applying direct pipelines | Projects containing both deployment strategies |

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

## Destructive Operations

StreamBuild can destroy selected deployed pipelines while retaining their authored definitions,
managed sources, and replay data. A target reset additionally removes managed source and replay
relations, but preserves every `_streambuild_*` metadata table, account and authorization state,
Kafka offsets, and the reset's own run evidence.

```bash
stb destroy --target uat --select pipeline:pl__orders pipeline:pl__reporting
stb reset-target --target uat
```

Both commands require an interactive terminal. They print a frozen impact plan, require a separate
review decision, and then prompt for exact pipeline-name challenges from that plan. There is no
non-interactive approval option or administrator bypass. Execution locks the target, replans, and
rejects manifest or warehouse drift before the first drop. Unselected downstream pipelines block a
plan rather than being silently included. Standalone CLI execution also requires the local OS user
to be an active built-in administrator in the StreamBuild control store.

UI plans and their review state are durable, actor-bound, and atomically single-use across server
restarts and workers.

The Pipelines UI exposes the same planner and executor through multi-selection and the dedicated
`pipeline.destroy` and `target.reset` permissions. Every generated statement, actor, challenge,
result, and observed remaining object after a partial failure is retained in Runs. A failed residual
catalog read is recorded as unavailable rather than as an empty target.

## Development UI

`stb dev` serves a warehouse-backed interface for one resolved project and target. It provides:

![StreamBuild lineage view showing the orders demo pipeline](https://raw.githubusercontent.com/chio-labs/streambuild/main/.github/streambuild-ui.png)

- overview, lineage, pipeline, catalog, source, topic, and message inspection
- connected plan previews and protected-pipeline confirmation
- direct, virtual, and mixed build execution
- deployment inventory, diff, promotion, and cleanup
- frozen bulk pipeline destruction and target reset plans with typed confirmation
- durable run timelines, statement progress, cancellation, and stale-run recovery guidance
- quality history, scheduler health, sensors, and dead-letter recovery

Run observability is warehouse-backed. A silent run becomes `unresponsive` after 45 seconds and
`presumed_failed` after `[defaults].run_presumed_failed_after` (default `10m`). A new build is blocked
until that safety window expires to prevent overlapping warehouse writes.

Shared installations support trusted-proxy or password authentication with project-scoped roles.
See the [documentation](https://docs.streambuild.dev) for access control and
operational configuration.

## Guarantees

- `stb compile` is connection-free and writes disposable artifacts under `target/`.
- `stb plan` is read-only; `stb build` always replans against current warehouse state.
- Lifecycle state is append-only metadata in the selected target database.
- Failed or cancelled builds are rerun, never resumed from copied SQL artifacts.
- Workflow statements execute serially to avoid unbounded ClickHouse memory pressure.

## Documentation

- [Documentation](https://docs.streambuild.dev)
- [Quickstart guide](https://docs.streambuild.dev/quickstart)
- [Runnable orders demo](examples/orders_demo/README.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Development

Install the locked Python and UI dependencies before running the verification lanes:

```bash
uv sync --locked --all-groups
make ui-install ui-build
make check-ci
make ui-verify
make test
```

Run every verification lane with:

```bash
make test-all
```

The integration and browser lanes provision real ClickHouse and Redpanda containers, so Docker must
be running. Install Chromium and its system dependencies before the first browser run:

```bash
uv run playwright install --with-deps chromium
make ui-install ui-build
make test-browser
```
