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
  pl__orders/
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

[build]
max_pipelines = 20

[targets.dev]
database = "analytics"

[targets.prod]
database = "analytics_prod"

[targets.prod.build]
max_pipelines = 10
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

Pipeline names must start with `pl__` by default. Configure or disable the prefix with:

```toml
[naming]
pipeline_prefix = "custom__" # Use "" to allow unprefixed names.
```

For a stricter rule, configure a naming macro:

```toml
[naming]
pipeline_naming_macro = "pipeline_name"
```

```python
from streambuild.compiler.macros.models import PipelineNamingContext

def pipeline_name(ctx: PipelineNamingContext) -> str:
    return ctx.name if ctx.source_name is None else f"pl__{ctx.source_name}"
```

The optional macro receives an immutable context containing the pipeline name, source, sorted model
names, relative directory, and mode. It returns the required directory name. A mismatch fails
discovery; compile, plan, and build never rename files.

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

Expensive replay roots can constrain adapter query settings without changing live materialized-view
ingestion. Pipeline defaults apply first:

```toml
[execution.replay.settings]
max_threads = 8
max_block_size = 64
```

A table model can override individual settings for its own replay:

```sql
MODEL (
  execution_settings (
    replay (max_block_size 32)
  )
);
```

Effective replay settings are shown in plans and apply only to replay `INSERT ... SELECT`
statements. They do not alter table storage settings, audits, or live ingestion.

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

An optional `[build].max_pipelines` is an absolute limit on the distinct pipelines in the final
expanded build scope. A target-specific `[targets.<name>.build].max_pipelines` replaces the project
default and requires that default to be configured. The limit cannot be authored in
`streambuild_local.toml`; local-only targets inherit the committed project default.

Direct pipelines can declare an operator gate in `pipeline.toml`:

```toml
mode = "direct"

[protection]
warning = "Interrupts protected order processing."
confirmation = "DEPLOY_ORDERS"
```

Every protected pipeline in a build requires its exact configured `--confirm` value, even with
`--auto-approve`. Interactive builds prompt for each missing confirmation. Virtual pipelines cannot
declare `[protection]`.

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

Lineage activity is separate from replay freshness. StreamBuild prefers ClickHouse
`system.query_views_log`, then insert-only `system.part_log` evidence. Enable the `query_views_log`
and `part_log` server log sections and set `log_query_views = 1` for ingestion users to get exact
materialized-view activity. If both logs are unavailable, recent `system.parts` modification time is
shown as approximate evidence because background merges can also modify parts. Missing evidence is
reported as unknown rather than stalled.

### Authentication

Local `stb dev` uses explicit disabled authentication and a deterministic local administrator.
Shared servers choose either trusted-proxy or password authentication at runtime.

Apache/PAM, GSSAPI, OIDC proxies, and similar upstreams use trusted-proxy mode:

```bash
stb dev \
  --auth-mode trusted_proxy \
  --auth-username-header X-Mustard-User \
  --control-store-url sqlite:////var/lib/streambuild/control.db
```

The proxy must replace the configured identity header with its authenticated user. A new valid
proxy identity is atomically provisioned as `viewer`; a missing identity returns `401`. Operators
own the network trust boundary and may use loopback binding, firewalling, or accepted on-premises
network trust.

Standalone password mode uses the packaged `/login` page and server-side sessions:

```bash
stb dev --auth-mode password --control-store-url postgresql+psycopg://user:password@db/streambuild
```

Bootstrap the first account without a ClickHouse connection:

```bash
stb admin --control-store-url sqlite:////var/lib/streambuild/control.db create-user \
  --username kevinl --authentication-source trusted_proxy --role admin
```

For password accounts, the command securely reads the password from an interactive prompt or
standard input. Existing administrators manage accounts in the Users UI; the CLI remains the
break-glass recovery path. Control-store URLs and authentication runtime settings can instead use
the `STREAMBUILD_CONTROL_STORE_URL`, `STREAMBUILD_AUTH_MODE`, and related `STREAMBUILD_AUTH_*`
environment variables shown by `stb dev --help`. Account state never belongs in ClickHouse or
`streambuild_project.toml`.

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

Tests are split into independent unit, ClickHouse integration, non-browser E2E, and browser E2E
lanes. Run them individually or use `make test-all` for the complete local suite:

```bash
make test
make test-integration
make test-e2e
make test-browser
```

Browser E2E tests exercise the packaged UI served by the real `stb dev` process, not Vite or
browser-intercepted APIs. Docker must be running because the tests provision real ClickHouse and
Redpanda containers on isolated networks. Install Chromium and its system dependencies before the
first run:

```bash
uv run playwright install --with-deps chromium
make ui-install ui-build
make test-browser
```

The browser lane is marker-owned, fixed to Chromium, and capped at two pytest workers to keep the
real services within predictable resource limits. CI runs the same target in the required
`Packaged Chromium E2E tests` job and treats Docker provisioning failures as failures rather than
skips.

Browser output is replaced under `test-results/` on each run. Every test records browser console,
page, request, response, and `stb dev` process diagnostics in its output directory. Failed tests also
retain a Playwright trace, video, and screenshot. CI uploads the complete directory as the
`playwright-browser-artifacts` artifact for seven days; inspect a downloaded trace with
`uv run playwright show-trace path/to/trace.zip`.
