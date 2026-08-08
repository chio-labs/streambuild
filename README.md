<p align="center">
  <img src="https://raw.githubusercontent.com/chio-labs/streambuild/main/.github/streambuild-logo-dark.png" alt="StreamBuild" width="100%">
</p>

<p align="center">
  Declarative ClickHouse streaming pipeline deployment for staged backfill, audit, and publish workflows.
</p>

`streambuild` is for streaming data teams that want SQL-authored models with deployment semantics
that fit live ClickHouse pipelines. Pipelines can build directly into live relations or stage a
virtual deployment for audit and promotion.

- compile a project-wide dependency graph before opening a warehouse connection
- inspect exact rebuild and replay work before applying it
- rebuild live relations directly or stage deployment-specific shadows
- replay retained history through the same model graph
- run SQL tests, audits, freshness checks, and scheduled quality checks

The current product is centered on ClickHouse and streaming replay semantics. Kafka-backed sources work today, and adopted external streaming tables are now supported as replay roots.

## Current Status

Current implemented workflow:

- `stb plan`
- `stb build`
- `stb test`
- `stb audit`
- `stb dev`
- `stb discover`
- `stb deployment list`
- `stb deployment show <deployment-id>`
- `stb deployment audit <deployment-id>`
- `stb deployment promote <deployment-id>`
- `stb doctor`
- `stb repair active-view`
- `stb reconcile`
- `stb compile`
- `stb janitor`

Current rollout model:

- `plan` is read-only
- direct `build` applies relation changes immediately
- virtual `build` starts a real staged deployment
- mixed `build` stages virtual pipelines first, then applies direct pipelines
- `deployment audit` inspects staged readiness
- `deployment promote` switches stable logical views to staged physical tables
- `janitor` remains the top-level retention and cleanup command

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
    orders_enriched.sql
    order_rollups.sql
```

Rules:

- each direct child folder under `pipelines/` is one pipeline
- recursive `*.sql` files under that folder belong to that pipeline
- pipeline name is inferred from the folder name
- pipeline source is inferred transitively from model driving inputs
- model name is inferred from the SQL filename stem
- optional `pipeline.toml` stores mode, naming, replay, audit, and protection overrides
- `pipeline.toml` can override the project build mode with `mode = "direct"` or `mode = "virtual"`
- each table pipeline resolves to one source, but one source may feed multiple pipelines

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

[defaults]
pipeline_mode = "virtual"
managed_source_ttl = "_replay_landed_at + INTERVAL 14 DAY"
model_ttl = "event_at + INTERVAL 30 DAY"
kafka_broker_list = "kafka1:9092,kafka2:9092"

[connection]
host = "localhost"
port = 8123
username = "clickhouse"
password = "${ENV:CLICKHOUSE_PASSWORD}"

[naming]
table_prefix = "tbl__"
view_prefix = "view__"

[targets.dev]
database = "analytics"
```

Notes:

- `name` and `default_target` are required; `adapter` defaults to `clickhouse`
- `[defaults].pipeline_mode` is `direct` unless explicitly set to `virtual`
- `streambuild_local.toml` may override the default with `[defaults].pipeline_mode`
- target selection is CLI `--target`, local `target`, then project `default_target`
- CLI `--vars` accepts one JSON object for `${name}` interpolation
- connection templates are expanded only for commands that connect
- metadata lives in the same database by default
- managed Kafka sources inherit `[defaults].kafka_broker_list` when they omit
  `broker_list`; a source-level value overrides the project default
- table models inherit `[defaults].model_ttl` when `MODEL(...)` omits `ttl`; an explicit model TTL
  overrides it, and the effective expression is validated against that model's output columns
- model relation names use the model's exact `relation_name`, then pipeline, project, and built-in
  kind-specific prefixes
- connection precedence is CLI flags, fixed `STREAMBUILD_CLICKHOUSE_*` environment
  variables, local config, selected target, then project config

### Warehouse Metadata

StreamBuild keeps append-only metadata in the target database. Authoritative virtual-environment
lifecycle state uses `_streambuild_schema_versions`, `_streambuild_virtual_deployments`,
`_streambuild_virtual_object_state`, `_streambuild_virtual_replay_boundaries`, and
`_streambuild_virtual_publications`.

Direct mode treats project declarations, the live catalog, and live source/target data as
authoritative. It captures replay boundaries in process memory rather than checkpoint tables.
`_streambuild_direct_fingerprints` contains optional successful-build SQL baselines for plan diffs;
missing or inaccessible direct fingerprint metadata does not block materialization.

`_streambuild_invocations` and `_streambuild_node_results` hold bounded terminal history for build,
audit, and test UI views. Their contents never influence planning, replay, publication, repair,
reconcile, or cleanup decisions. Builds require the current observability schema and a dedicated
ClickHouse observation connection before planning; observation failures after execution starts do
not interrupt warehouse work.

Every build also emits append-only `_streambuild_run_events`, including a heartbeat every 10 seconds.
The dev server derives `running`, `unresponsive` after 45 seconds, and `presumed_failed` after 10
minutes without persisting guessed outcomes. These states are reversible when a later heartbeat or
terminal fact arrives. UI cancellation signals only a child owned by the current dev-server process;
orphaned and CLI-launched runs remain observable but cannot be signalled by that server. Recovery is
always rerun, never resume.

Mutating commands are single-writer operations per target database. Do not run concurrent direct
builds, publishes, repairs, reconciles, or cleanup operations against the same target. Independent
virtual builds remain isolated through deployment-specific physical relation names and
deployment-scoped append-only rows.

Build workflow statements currently execute serially and there is no `threads` setting. This is
intentional: replay statements can consume most of a small ClickHouse host's memory on their own.
Concurrency should only be introduced with warehouse-aware resource limits rather than as an
unbounded thread count.

### Model Relation Naming

Models normally omit `relation_name`. Table models use `[naming].table_prefix` and view models use
`[naming].view_prefix`, followed by the SQL filename stem:

```toml
# streambuild_project.toml
[naming]
table_prefix = "event__tbl_"
view_prefix = "event__view_"
```

An optional `pipeline.toml` `[naming]` block overrides either project prefix for that pipeline.
An explicit `MODEL (relation_name ...)` has highest precedence and should be reserved for genuine
exceptions.

`kafka__`, `raw__`, and `mv__` are framework-owned prefixes. Compilation rejects an effective model
relation beginning with one of them, whether it came from an explicit `relation_name`, a pipeline
prefix, or the project default. Deployment-suffixed physical-name lookalikes and project-wide
relation collisions are also compile errors.

## Pipeline Sources

Reusable replay-driving sources live under `sources/*.yml`. StreamBuild follows each table model's
`__source(...)` or untyped `__ref(...)` driving input until it reaches a registered source. Every
pipeline containing tables must resolve to exactly one source. Terminal views do not participate in
source inference, so a view-only pipeline is valid and source-less.

### Managed Kafka Landing

```yaml
sources:
  - kind: kafka
    name: orders
    topic: source.orders.created
    ttl: _replay_landed_at + INTERVAL 30 DAY
    replay_boundary:
      mode: offsets
```

This is the managed source shape:

- StreamBuild creates the Kafka table
- StreamBuild creates the raw landing table and landing MV
- source `broker_list` overrides `[defaults].kafka_broker_list`; one of them is required
- source `ttl` overrides `[defaults].managed_source_ttl`; omitting both keeps data indefinitely
- default consumer groups are scoped to the target database
- when a landing is genuinely new, `stb build` clears orphaned committed offsets before consuming
  from the earliest available message
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

### Pipeline Build Modes

`[defaults].pipeline_mode` sets the project default:

```toml
[defaults]
pipeline_mode = "direct"
```

A pipeline can override that default in its own `pipeline.toml`:

```toml
mode = "virtual"
```

Direct pipelines may reference direct pipelines, and virtual pipelines may reference virtual
pipelines. Model relationships cannot cross the mode boundary in either direction; shared sources
remain valid. `stb plan` and `stb build` accept mixed selections. They stage the virtual phase
first and only start the immediately-applied direct phase after virtual staging succeeds.
The CLI asks for confirmation once and reports the staged deployment separately from live direct
changes. `--full-refresh` and `--deployment-id` apply to the virtual phase.

Virtual-environment projects can choose change-driven replay independently from the
fallback used when bounded replay cannot preserve aggregate history:

```toml
bounded_replay_fallback = "bounded_without_history"

[replay_on_change]
breaking = "full"
non_breaking = "bounded-7d"
```

This optional `pipeline.toml` sits directly in the pipeline directory. The same policies can be
defaults in `streambuild_project.toml` and overrides in a model `MODEL(...)` header. Pipeline- and
model-level replay policies are rejected for pipelines whose effective mode is direct.

### Protected Pipelines

Add `[protection]` to a pipeline's `pipeline.toml` when rebuilding it has operational impact:

```toml
[protection]
warning = "Interrupts the protected trading price feed while objects are replaced."
confirmation = "DEPLOY_PROTECTED_PRICES"
```

The warning defaults to a generic protected-pipeline message. `confirmation` defaults to the
pipeline name when it is already a shell-safe token, or a `CONFIRM_`-prefixed sanitized name
otherwise, so an empty `[protection]` block is valid. A protected pipeline in the resolved build
closure always requires its exact confirmation. `--auto-approve` does not bypass this gate:

```bash
stb build --select pipeline:protected_prices --auto-approve \
  --confirm DEPLOY_PROTECTED_PRICES
```

Repeat `--confirm` when one build touches multiple protected pipelines. The development UI displays
the same warning and will not start the subprocess until every required value matches.

### Audit Policy And Scheduling

Audit defaults can set severity, cadence, and post-build warmup:

```toml
[defaults.audits]
severity = "warning"
every = "1h"
warmup = "5m"

[targets.dev.audit_scheduler]
enabled = true
```

Pipelines can override these values under `[audit_defaults]` in `pipeline.toml`, and individual
audits can override them in `AUDIT(...)`. A direct build records warmup-delayed audits as deferred
rather than running them too early. `stb audit` respects warmup; `stb audit --force` bypasses it.

The scheduler runs inside `stb dev` when it is enabled for the selected target. It claims cadence
slots in ClickHouse so repeated scheduler ticks do not duplicate the same logical audit attempt.
The Quality page shows scheduler health, due times, recent outcomes, severity, and warmup state.

## Models

Each SQL model starts with a `MODEL (...)` header. Models default to streaming tables.

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
- for table models only, additional `__ref(...)` dependencies must declare `ref_type`
- header fields use SQLBuild syntax: whitespace-separated `key value` entries, lists in `[...]`, and nested mappings in `(...)`
- omitted SQL storage settings default to `engine "MergeTree()"` and `order_by ["_replay_timestamp"]`
- both `CAST(expr AS Type)` and `expr::Type` are accepted

### Terminal Views

An ordinary query view uses `kind view` and may read any number of upstream sources or models:

```sql
MODEL (
  kind view,
  relation_name customer_orders,
);

SELECT
  orders.order_id::UInt64 AS order_id,
  payments.amount_cents::UInt64 AS amount_cents
FROM __ref("orders") AS orders
JOIN __ref("payments") AS payments USING (order_id)
```

Views have no driving input, storage settings, replay policy, or replay work. View refs reject
`ref_type`; every `__source(...)` and `__ref(...)` is an ordinary query dependency. A view must be a
terminal node across the complete project graph: no table or view model may reference it. Tests and
audits may target it. `relation_name` is an exact warehouse relation override for either model kind;
without one, table and view names use the effective `table_prefix` or `view_prefix` from optional
pipeline `[naming]`, project `[naming]`, then the `tbl__` and `view__` defaults. `kafka__`, `raw__`,
and `mv__` remain framework-reserved.

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
uv run stb test
uv run stb audit
uv run stb dev
uv run stb deployment list
uv run stb deployment show <deployment-id>
uv run stb deployment audit <deployment-id>
uv run stb deployment promote <deployment-id>
uv run stb doctor
uv run stb repair active-view --table tbl__orders
uv run stb reconcile
uv run stb compile
uv run stb janitor
```

## Development UI

Run the packaged UI and API from the project root:

```bash
uv run stb dev
```

The server binds to `127.0.0.1:8000` by default. Use `--ui-host` and `--ui-port` to change that.
The UI includes:

- project overview, pipeline detail, catalog, and lineage views
- connected plan inspection and protected-pipeline confirmation
- single-flight build execution with live statement events and owned-process cancellation
- durable run and quality history, including unresponsive and presumed-failed states
- source throughput, retained rows, storage, freshness, and Kafka consumer lag
- broker topic inventory, defaulting to topics managed by the current project
- a warehouse-backed source message browser with JSON predicates, facets, time or offset ranges,
  stable columns, cursor pagination, and full-record inspection up to 16 MiB

The message browser reads retained landing rows from ClickHouse. It does not consume messages from
Kafka or advance consumer offsets. Broker metadata and lag are loaded separately and failures are
reported without making the rest of the project UI unavailable.

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
    audits/
    tests/
  run/
    plan/
      plan.json
      workflow.template.sql
      steps/*.sql.template
    build/
      plan.json
      execution.json
      workflow.sql
      steps/*.sql
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
- logical DAG identity

For direct mode, `stb plan` publishes deterministic workflow templates because live replay cutoffs do
not exist yet. `stb build` publishes the exact attempted SQL plus `execution.json`, including terminal
status, captures, completed steps, and failure evidence. Re-executing a build workflow reuses those
exact captured boundaries rather than recapturing newer source rows.

For a single-mode selection, `stb plan` atomically replaces `target/run/plan/plan.json` with the
complete connected plan. JSON stdout is byte-identical to this disposable visibility artifact. A
mixed plan emits one combined text or JSON document but does not flatten its two phase workflows
into one artifact. StreamBuild never reads `target/run/` as warehouse state, and deleting `target/`
does not affect subsequent commands.

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
