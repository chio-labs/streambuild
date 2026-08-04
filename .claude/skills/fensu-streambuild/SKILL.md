---
name: "fensu-streambuild"
description: "Use when modifying the streambuild project governed by fensu.toml. Includes Fensu configuration, commands, FF diagnostics, repository architecture, and multi-module Python call-flow work."
---

<!-- generated-by: fensu skills -->
<!-- fensu-skill-owner: {"content_fingerprint":"505d4e24e9f6152787941b367ee9706269c500ccd025b1c2e4c740b09412d0b4","identity":"fensu-streambuild","input_fingerprint":"b9dc6d37e8839d41f1f2267ff7149ca209568b83580ea9cdb9af2c909d47e3f7","owner":"c8ca2b2833426e659f1f9431f5534ee7e891ee25b62edf3194bd00c83975d53e","schema":1} -->

# Fensu

Fensu checks code ownership, dependency boundaries, module roles, function shape, and test conventions. This skill is generated from the repository's active rules.
Load this guidance before running any `fensu` command or changing Fensu configuration.

## Commands

- Run `fensu check` after architecture-relevant changes.
- Run `fensu rule <CODE>` to inspect a diagnostic and its remediation.
- Run `fensu map <SYMBOL>` for proven callees, or add `--direction upstream` for proven callers.
- Run `fensu skills` after changing rule selection or custom rules.

## Navigation And Work Handoffs

For any non-trivial change that crosses module or package boundaries, run `fensu map <symbol> --depth 4` before editing. Rerun the same map after implementation to explain the changed flow. Skip only isolated single-file edits.

Treat the map as a deterministic call skeleton whose primary benefit is helping the user understand the system, not proving that the agent explored it. Do not paste a raw map as the handoff. Read the relevant source to explain purpose and branches, use the diff to identify what changed and why, and use checks and tests to state what was verified. Never guess through unresolved calls. If the map cannot resolve the flow, state that and continue with direct source inspection.

After a substantial chunk of work, rerun `fensu check` and the same map. Include a user-facing walkthrough only when it materially clarifies a multi-module change. Default to the smallest affected branch, normally three to eight lines:

```text
build_result(...)                           domain/main/build.py:24
└── assemble_result(...)                    domain/_helpers/assemble.py:41
    CHANGED: state the behavioral difference and why it was made.
VERIFIED: name the check that proves the changed boundary.
```

Replace the template with facts from the repository. Preserve enough parent context to orient the user, but omit unchanged branches that do not aid understanding. Use a full before/after walkthrough only when ownership or phase boundaries changed substantially. `DONE`, `PENDING`, and `WE ARE HERE` are agent-authored work-state annotations, not Fensu output.

Every displayed function must include its repository-relative path and line when available. Mark changed nodes with `CHANGED` and explain the behavioral difference and reason, not merely that a file changed. Mark supporting evidence with `VERIFIED`. When static mapping omits protocol or dynamic dispatch, stitch in the continuation only after confirming it from source and label it `SOURCE-RESOLVED DYNAMIC BOUNDARY` so the user can distinguish map output from inspected runtime wiring.

Do not force a graph into a handoff when one sentence with a clickable `path:line` communicates the change more clearly.

## Working With Existing Drift

The user request defines the scope of remediation. A large fault count is an architectural baseline, not authorization to fix unrelated code.

- If the user requests one change, do not expand into unrelated fault remediation.
- If the user explicitly requests a broader refactor, particular fault families, or zero faults, treat that broader target as authorized scope.
- Satisfy faults by improving code under the current policy. Do not weaken selection, thresholds, exceptions, or custom rules unless the user explicitly requests a policy change.
- Before moving or splitting behavior, map the affected call flow and run the existing tests.
- When coverage around changed behavior is weak or unknown, add focused characterization tests before refactoring.
- Preserve behavior first and improve structure in verifiable slices.
- Distinguish pre-existing faults from regressions introduced by the current work.

For an explicitly authorized broad refactor, capture the baseline, map affected flows, establish characterization coverage, work in coherent slices, verify each slice, and run full final verification. A request to make `fensu check` pass means fix the code under the current policy, not edit configuration until findings disappear.

## Testing Refactors Safely

Before materially restructuring behavior, inspect the existing tests. When the affected behavior is weakly covered or its coverage is uncertain, add focused characterization tests before moving code.

Use the cheapest test that faithfully exercises the risk:

- Unit tests for isolated decisions, transformations, and error handling.
- Integration tests for storage, messaging, process, and adapter boundaries.
- End-to-end tests for user-visible commands and workflows.
- Real local dependencies when they are deterministic and reasonably inexpensive.

Prefer faithful local infrastructure over mocks when behavior depends on the real system. Useful options include PostgreSQL, Redis, Kafka or Redpanda, RabbitMQ, NATS, MinIO, OpenSearch, and similar services available through testcontainers.

Before using testcontainers, check whether a functioning container runtime is available. Prefer `docker info`; if Docker is unavailable, check `podman info` and whether a compatible Docker API socket is configured. Finding the executable alone is not enough: verify the runtime can actually start containers. When a functioning runtime is available, testcontainers is an appropriate default for integration behavior that mocks cannot faithfully represent. Record the container-runtime requirement in the test documentation or final change summary.

Use SQLite or DuckDB when they faithfully represent the tested contract. Do not use SQLite as evidence for PostgreSQL-specific SQL, transactions, locking, concurrency, extensions, or type behavior.

Tests requiring real remote credentials or services such as Salesforce or Snowflake remain a user and project decision.

When concurrency, retries, duplicate delivery, locking, or shared mutable state are real risks, add deterministic race-oriented tests where practical. Force relevant interleavings with barriers, events, controlled workers, or transactional locks rather than relying on sleeps. Assert atomicity, idempotency, ordering, uniqueness, and retry behavior as appropriate.

Do not duplicate every assertion at unit, integration, and end-to-end levels. Each layer should prove a boundary that cheaper tests cannot prove faithfully.

## Test Execution And Isolation

Use the repository's established verification commands first. When pytest-xdist is installed and the relevant suite supports parallel execution, prefer:

```bash
pytest -n auto
```

Write new tests so they can execute independently whenever practical:

- Use unique temporary paths, databases, schemas, ports, and resource names.
- Do not depend on test execution order.
- Isolate environment changes with fixtures such as monkeypatch.
- Avoid shared process-global mutation.
- Give each worker independent external state where concurrent access would alter the result.
- Make cleanup safe after both success and failure.

When some tests genuinely require sequential execution, separate them from the parallel-safe suite. Run independent batches concurrently only when they do not share mutable resources. Otherwise run the required batches in sequence, while still using xdist inside each parallel-safe batch.

If failures suggest broken isolation, rerun the failing tests sequentially and then rerun the relevant suite sequentially. A sequential pass does not make the problem acceptable: identify and correct the shared state, ordering dependency, port collision, database collision, or timing assumption where reasonable.

## Repository Structure

Only structures established by this repository's active core rules are shown. Omitted structures are not implied.

### Runtime

Leaf domain:

```text
src/streambuild/
└── <domain>/
    ├── main/
    ├── _helpers/
    ├── classes/
    ├── models.py
    ├── types.py
    ├── constants.py
    └── exceptions.py
```

Branch domain:

```text
src/streambuild/
└── <domain>/
    └── <subdomain>/
        ├── main/
        ├── _helpers/
        ├── classes/
        ├── models.py
        ├── types.py
        ├── constants.py
        └── exceptions.py
```

### Domain Shape

Domains may be leaves with role content directly beneath `<domain>/`, or branches containing named subdomains. Do not mix the two shapes.

For a singleton capability, prefer a leaf instead of creating a placeholder `core` subdomain.

Promote a leaf to a branch only when multiple real capabilities exist.

Every leaf domain or subdomain must contain a direct `main/` boundary with at least one non-`__init__.py` Python entry module. Branch-domain parents do not need their own `main/`; their leaf subdomains do.

Do not add placeholder `main/` packages. If a package owns only passive models, types, constants, exceptions, or classes, move them into the closest domain or subdomain whose `main/` behavior owns and uses them.

Generic package names are banned, including `base`, `common`, `lib`, `misc`, `shared`, `util`, and `utils`. Name the business domain or technical capability owner instead.

### Role Containers

#### `_helpers/`: Flat Or Grouped

Each `_helpers/` container has an effective module limit; its configured role base is 10.

```text
_helpers/
├── first_helper.py
└── second_helper.py
```

or group every module:

```text
_helpers/
├── reading/
│   └── read_helper.py
└── writing/
    └── write_helper.py
```

#### `main/`: Flat Or Grouped

Each `main/` container has an effective module limit; its configured role base is 20.

```text
main/
├── first_entry.py
└── second_entry.py
```

or group every module:

```text
main/
├── reading/
│   └── read_entry.py
└── writing/
    └── write_entry.py
```

Every container holds direct Python modules or Python-containing buckets, never both. Empty and asset-only directories do not count as buckets.

Configured base `max_role_depth` is 1. Role tables and matching path overrides can provide the effective per-path value.

Runtime role names are banned as buckets: `main`, `_helpers`, `classes`, `models`, `types`, `constants`, and `exceptions`.

Generic bucket names remain FFR204 concerns and do not receive a second container-layout fault.

Fixed role filenames such as `models.py`, `types.py`, `constants.py`, and `exceptions.py` are sibling roles and must never be nested beneath `_helpers/`.

Every non-`__init__.py` module whose first structural role is `main` is an entry module, including grouped main modules. Entry shape and container depth are orthogonal, so an over-depth main path may independently receive both layout and entry-shape diagnostics. A `main` bucket below another role is not an entry boundary.

### Role Examples

#### `main/read_invoice.py`

Expose exactly one public entry function and keep phase work in _helpers/. Use up to two private functions only when entry-specific glue is genuinely needed:

```python
from streambuild.invoices._helpers.loading import load_invoice
from streambuild.invoices._helpers.normalization import normalize_invoice
from streambuild.invoices.models import Invoice

def read_invoice(invoice_id: str) -> Invoice:
    loaded: Invoice = load_invoice(invoice_id)
    return normalize_invoice(loaded)
```

#### `models.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Invoice:
    identifier: str
    total_cents: int
```

When Pydantic is already in use, its structured models belong in the same role:

```python
from pydantic import BaseModel

class InvoiceQuery(BaseModel):
    customer_id: str
    include_paid: bool = False
```

#### `_helpers/normalization.py`

Private constants and support dataclasses precede helper functions:

```python
from dataclasses import dataclass

_DEFAULT_CURRENCY: str = "USD"

@dataclass(frozen=True, slots=True)
class _NormalizedAmount:
    cents: int
    currency: str

def normalize_amount(cents: int) -> _NormalizedAmount:
    return _NormalizedAmount(cents=max(cents, 0), currency=_DEFAULT_CURRENCY)
```

#### `classes/invoice_repository.py`

Each module under `classes/` defines exactly one top-level class:

```python
from streambuild.invoices.models import Invoice

class InvoiceRepository:
    def __init__(self, invoices: dict[str, Invoice]) -> None:
        self._invoices = invoices

    def read(self, invoice_id: str) -> Invoice:
        return self._invoices[invoice_id]
```

#### `types.py`

```python
from enum import StrEnum
from typing import NewType, TypeAlias

InvoiceId = NewType("InvoiceId", str)
InvoiceLine: TypeAlias = tuple[str, int]

class InvoiceState(StrEnum):
    DRAFT = "draft"
    PAID = "paid"
```

#### `constants.py`

```python
DEFAULT_PAGE_SIZE: int = 100
MAX_RETRY_ATTEMPTS: int = 3
```

#### `exceptions.py`

```python
class InvoiceNotFoundError(LookupError):
    """Raised when an invoice identifier is unknown."""
```

### Tests

```text
tests/
└── <scope>/
    └── src/streambuild/<domain>[/<subdomain>]/
        ├── _test_types.py
        └── test_feature.py
```

Tooling-backed tests mirror under `tests/<scope>/scripts/<area>/`.

`_test_types.py`:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ReadInvoiceTestCase:
    description: str
    invoice_id: str
    expected_identifier: str
```

`test_feature.py`:

```python
import pytest

from streambuild.invoices.main.read_invoice import read_invoice
from streambuild.invoices.models import Invoice
from tests.unit.src.streambuild.invoices._test_types import ReadInvoiceTestCase

@pytest.mark.parametrize(
    "test_case",
    [
        ReadInvoiceTestCase(
            description="returns the requested invoice",
            invoice_id="invoice-1",
            expected_identifier="invoice-1",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invoice_id_when_reading_invoice_then_returns_expected_invoice(
    test_case: ReadInvoiceTestCase,
) -> None:
    result: Invoice = read_invoice(test_case.invoice_id)

    assert result.identifier == test_case.expected_identifier
```

### Tooling

```text
scripts/
├── run_tool.py
└── <tool>/
    ├── main/
    ├── _helpers/
    ├── classes/
    └── rules/
```

## Effective Project Configuration

This is the loaded effective configuration, not a template. Lists and mappings are rendered deterministically; path-threshold declarations retain declaration order because that order breaks equally specific matches.

- Configuration source: "fensu.toml"
- Project root from installation root: "."
- Installation root: "."
- Current skill identity: "fensu-streambuild"
- Complete loaded catalogue size: 118

### Scopes

- Product roots: ["src/streambuild"]
- Test roots: ["tests"]
- Tooling roots: ["scripts"]

### Configured Rule Selectors

- Blocking selectors (`select`): ["FF", "XSTB"]
- Warning selectors (`warn`): []
- Ignore selectors (`ignore`): []

### Resolved Rule Sets

- Blocking rule codes: ["FFA001", "FFA002", "FFA101", "FFA102", "FFA103", "FFH001", "FFH002", "FFH003", "FFH004", "FFH005", "FFH006", "FFH007", "FFH008", "FFH009", "FFL001", "FFL002", "FFL101", "FFL102", "FFL103", "FFL104", "FFL105", "FFL110", "FFL301", "FFN001", "FFN002", "FFN003", "FFN004", "FFR001", "FFR002", "FFR003", "FFR004", "FFR101", "FFR102", "FFR103", "FFR104", "FFR201", "FFR202", "FFR203", "FFR204", "FFR205", "FFR301", "FFR302", "FFR303", "FFR304", "FFR305", "FFR306", "FFR307", "FFR308", "FFR309", "FFR401", "FFR402", "FFR403", "FFR404", "FFR405", "FFR406", "FFR501", "FFR502", "FFR503", "FFR601", "FFR701", "FFR702", "FFR703", "FFR704", "FFR705", "FFR706", "FFR707", "FFS001", "FFS002", "FFS003", "FFS010", "FFS011", "FFS101", "FFS110", "FFS120", "FFS130", "FFS131", "FFS201", "FFT001", "FFT002", "FFT003", "FFT004", "FFT005", "FFT006", "FFT007", "FFT008", "FFT101", "FFT102", "FFT103", "FFT104", "FFT105", "FFT106", "FFT201", "FFT202", "FFT203", "FFT204", "FFT301", "FFT302", "FFT401", "FFT402", "FFT403", "FFT404", "FFT405", "FFT406", "FFT407", "FFT408", "FFT411", "FFT412", "FFT413", "FFT414", "XSTB001", "XSTB002", "XSTB003", "XSTB004", "XSTB005", "XSTB006", "XSTB007", "XSTB008"]
- Warning rule codes: []
- Ignored matched rule codes: []

Normal work must satisfy blocking policy. Warnings are review signals, not scope authorization. Run `fensu check --warn` after substantial changes when practical, and never delete code or change architecture solely because of an advisory warning without verifying the actual contract.

### Custom Rule Sources

- `rule_paths`: []
- `rule_modules`: ["scripts.fensu_policy.classes.workflow_authority_policy", "scripts.fensu_policy.rules.adapter_ownership", "scripts.fensu_policy.rules.observability_authority", "scripts.fensu_policy.rules.sql_analysis_boundary", "scripts.fensu_policy.rules.workflow_authority"]

### Cache And Evaluation

- Cache enabled: `true`
- Cache requires cacheable rules: `true`
- Evaluation include boundaries: []
- Evaluation exclude boundaries: ["tests/e2e/fixtures/**"]

### Effective Global Thresholds

- `max_arguments` = 10
- `max_distinct_calls` = 20
- `max_file_lines` = 2000
- `max_helpers_container_modules` = 10
- `max_locals` = 20
- `max_main_container_modules` = 20
- `max_positional_args` = 1
- `max_role_depth` = 1
- `max_script_entrypoint_lines` = 80
- `max_statements` = 40
- `max_statements_global` = 70
- `min_custom_rule_test_cases` = 1
- `min_shared_domain_prefix_packages` = 2

### Configured Role Threshold Overrides

- None.

### Configured Path Threshold Overrides

- None.

### Effective Naming Contracts

- "as_*" = "returns-value"
- "can_*" = "returns-bool"
- "enforce_*" = "no-return"
- "get_*" = "returns-value"
- "has_*" = "returns-bool"
- "is_*" = "returns-bool"
- "iter_*" = "returns-iterator"
- "supports_*" = "returns-bool"
- "to_*" = "returns-value"
- "validate_*" = "no-return"

### Configured Rule Exceptions

- Rule "FFT104"; path="tests/e2e/src/streambuild/executor/helpers.py"; scope=["wait_for_row_count", "wait_for_table_exists", "wait_for_table_missing"]; reason="The three wait_for_* helpers poll for state ClickHouse reaches asynchronously. A bounded retry loop and its early return are the wait condition, so they cannot be expressed branch-free. Every other conditional in this module has been removed."

### Configured Path-Scoped Rule Ignores

- None.

## Custom Rule Authority

Never create, configure, enable, disable, or materially change a custom rule unless the user explicitly requested it or explicitly approved your proposal.

An explicit request such as "create a custom rule preventing this" or "make Fensu enforce this convention" is already sufficient authorization. Do not ask for a redundant second confirmation.

When work reveals a recurring enforceable convention:

1. Complete the requested change under the existing policy.
2. Explain the recurring pattern or risk.
3. Suggest a possible custom rule and its intended boundaries.
4. Wait for explicit user approval before implementing it.

Never add or change policy merely because the current task exposed a possible convention, similar code appears more than once, a stricter architecture seems preferable, a core rule is inconvenient, or changing policy would make `fensu check` pass. Fix code under current policy rather than weakening or rewriting policy to avoid the work.

## RuleContext Public API

Approved custom rules receive `ctx: RuleContext`. Import authoring APIs only from the top-level `fensu` package. The five public analysis zones are:

- `ctx.facts`: `annotations()`, `assignment_references()`, `class_declarations()`, `comments()`, `comparisons()`, `complex_comprehensions()`, `dataclasses()`, `function_conditionals()`, `functions()`, `function_contracts()`, `hygiene()`, `meaningful_returns(name_patterns=())`, `local_call_edges()`, `module_declarations()`, `named_calls()`, `outer_state_mutations()`, `parameter_mutations()`, `parameter_mutation_occurrences()`, `project_calls()`, `project_functions()`, `references()`, `test_functions()`, `top_level_definition_conditionals()`, and `test_module()`.
- `ctx.text`: `source`, `line(line_number)`, and `slice(source_range)`.
- `ctx.syntax`: `handles(kind=None)`, `kind(handle)`, and `range(handle)`.
- `ctx.relations`: `parent(handle)`, `children(handle)`, and `ancestors(handle)`.
- `ctx.project`: dependency-recording cross-file and filesystem queries. Use `analysis(requester=ctx.path, path=path)`, `dataclasses(requester=ctx.path, path=path)`, `directory_entries(requester=ctx.path, path=path)`, `entrypoint_modules(requester=ctx.path)`, `module_function(requester=ctx.path, module_name=name, function_name=name)`, `python_anchor(requester=ctx.path, path=path)`, `exists(requester=ctx.path, path=path)`, `is_dir(requester=ctx.path, path=path)`, `is_file(requester=ctx.path, path=path)`, and `glob(requester=ctx.path, path=path, pattern=pattern, recursive=False)`. Inspect recorded observations with `dependencies()` or `dependencies_for(requester=ctx.path)`.

Position and ownership helpers: `ctx.path`, `ctx.repo_root`, `ctx.source`, `relative_parts()`, `repo_relative_parts()`, `scope_root()`, `scope_roots(scope)`, `module_parts()`, `scope()`, `role_of()`, `in_role(role)`, `is_entry_module()`, `is_main_module()`, `domain()`, and `subdomain()`. `role_of()` describes the current file here; use project facts rather than assuming arbitrary paths share its position.

AST helpers: `nodes(node_type)`, `call_name(node)`, `base_name(node)`, `top_level_functions(module)`, `non_docstring_body(module)`, `distinct_callees(fn)`, `assigned_locals(fn)`, `complex_comprehensions()`, `parameter_names(fn)`, and `inside_loop(node)`.

Policy helpers: `threshold(name=..., path=None)` and `contracts()`. Fault constructors: `fault(node=..., message=None, remediation=None)`, `fault_at(location=..., message=None, remediation=None)`, `fault_for(path=..., line=..., column=..., message=None, remediation=None)`, and `path_fault(path=None, message=None, remediation=None)`.

## Approved Custom Rule Authoring Lookup

When authoring an approved custom rule, use the generated RuleContext summary first. If exact signatures or returned public models are unclear, inspect existing repository custom rules, then the public Fensu exports and type definitions from the project's active Python environment. This targets the installed Fensu version rather than remembered or generic API knowledge.

It is acceptable to locate the active installation through `fensu.__file__` or the project's `.venv` and read definitions behind public exports such as `RuleContext`, semantic fact protocols, project-query protocols, and public result models. Consult public documentation after those installed public definitions. Read private implementation only to diagnose a suspected Fensu defect.

Only import authoring APIs from top-level `fensu`. Reading installed implementation for understanding does not make private `_helpers/` modules a supported dependency. Do not import from or couple custom rules to Fensu's private modules.

## Testing Custom Rules

Test approved custom rules through Fensu's real discovery and evaluation pipeline. Import the harness only from the top-level package and pass the decorated rule function as `rule=`. `RuleFile` support sources are available to `ctx.project` but are not direct evaluation targets.
The effective minimum is `1` statically declared `RuleCase` value(s) per configured custom rule, including rules not selected for blocking or warning evaluation. A value of `0` disables this requirement.

When FFT413 is active, do not parametrize directly with `RuleCase`. Parametrize with a dataclass imported from local `_test_types.py`, then construct `RuleCase` inside the test. A pair of apparently conflicting diagnostics should only be described as a policy gap after checking whether an adapter or wrapper pattern satisfies both rules.

`_test_types.py`:

```python
from dataclasses import dataclass

from fensu import RuleFile


@dataclass(frozen=True)
class CustomRuleTestCase:
    description: str
    path: str
    source: str
    expected_fault_count: int
    files: tuple[RuleFile, ...] = ()
    scope: str = "root"
    scope_root: str | None = None
```

`test_client_ownership.py`:

```python
import pytest

from fensu import RuleCase, RuleResult, evaluate_rule
from scripts.fensu_policy.rules.client_ownership import no_global_client
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="reports a forbidden global client",
            path="package/example.py",
            source="GLOBAL_CLIENT = build_client()\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="allows a function-local client",
            path="package/example.py",
            source="def run() -> None:\n    client = build_client()\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_when_checking_rule_then_returns_expected_faults(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=no_global_client,
        test_case=RuleCase(
            description=test_case.description,
            path=test_case.path,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            files=test_case.files,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count
```

Cover a failing example, a passing example, near misses, scope exclusions, deterministic ordering, and cross-file invalidation when the rule uses `ctx.project`. Verify cold and warm cache behavior. Dynamic case generators cannot prove the configured static minimum.

## Cacheability

Configured cache enabled: `true`. Configured `require_cacheable`: `true`.

Because `require_cacheable = true`, every selected custom rule must satisfy the cacheability contract.

Cacheable custom rules use only allowlisted pure imports; never call `open`, `eval`, `exec`, `input`, or `__import__`; perform no direct filesystem access; make every cross-file query through `ctx.project` with `requester=ctx.path`; and emit deterministic diagnostics. Configure concrete `rule_modules`. Keep decorated declarations in `rules/`, shared implementation in the sibling `_helpers/`, and constants in the policy package's sibling `constants.py`. A configured rule package does not mean helpers belong beneath `rules/`; that layout violates FFR704.

Verify cache behavior with separate commands so a deliberate baseline fault does not prevent later observations:

```bash
fensu check --no-cache
fensu check --cache-stats
fensu check --cache-stats
```

For a cacheable ruleset, the second cached run must report all hits, zero misses, `non_cacheable=0`, and diagnostics byte-identical to the uncached run.

## Blocking Rules

### FFA001: parameter-annotation

Family: `annotations`

function parameters must define type annotations

Remediation: Annotate every parameter with the value type accepted by the function.

### FFA002: return-annotation

Family: `annotations`

functions must define return type annotations

Remediation: Declare the returned value type, using None when the function returns no value.

### FFA101: module-variable-annotation

Family: `annotations`

module-level variables must define type annotations

Remediation: Add an explicit annotation to the first module-level assignment.

### FFA102: class-attribute-annotation

Family: `annotations`

class attributes must define type annotations

Remediation: Annotate the class attribute where it is first assigned.

### FFA103: local-variable-annotation

Family: `annotations`

local variables must define type annotations on first binding unless assigned a scalar literal

Remediation: Annotate first bindings whose type is not evident from a number, string, bool, bytes, or f-string literal.

### FFH001: single-line-docstrings

Family: `hygiene`

docstrings must be a single line; move extended explanation into docs or tests

Remediation: Keep one concise summary line and move extended rationale into documentation or tests.

### FFH002: no-standalone-comments

Family: `hygiene`

standalone comments are not allowed; prefer clear names or docs/tests

Remediation: Replace the comment with clearer names or move lasting explanation into documentation or tests.

### FFH003: no-raw-builtin-raise

Family: `hygiene`

runtime code must raise structured errors instead of raw built-in exceptions

Remediation: Raise a domain-specific exception from exceptions.py with a stable actionable message.

### FFH004: no-assert-in-runtime

Family: `hygiene`

runtime code must not use assert for invariants; raise a structured error

Remediation: Replace assert with an explicit guard that raises a domain-specific exception.

### FFH005: no-swallowed-exception-probe

Family: `hygiene`

runtime code must not swallow broad exceptions as existence probe answers

Remediation: Use an explicit metadata or existence check, or catch only the expected exception and preserve failures.

### FFH006: no-complex-comprehensions-in-tooling

Family: `hygiene`

nested or multi-generator comprehensions hide control flow and data shapes

Remediation: Extract a named helper when the transformation has a coherent purpose. For one-off local logic, use simple statements with named intermediate values instead of nested comprehension control flow.

### FFH007: no-unnamed-string-decisions

Family: `hygiene`

string literals must not directly control comparison behavior

Remediation: Name the decision value in constants.py or compare against an enum member so the branch expresses the concept it represents.

### FFH008: no-magic-numeric-comparisons

Family: `hygiene`

non-canonical numeric literals must not directly control comparisons

Remediation: Name the threshold or sentinel in constants.py and compare against that name; only -1, 0, and 1 are self-explanatory comparison values.

### FFH009: no-import-time-side-effects

Family: `hygiene`

runtime and tooling modules must not execute standalone calls during import

Remediation: Move the operation into an explicit function or assign a pure constructor result.

### FFL001: absolute-imports-only

Family: `layers`

use absolute imports; relative imports hide package boundaries

Remediation: Replace relative imports with an absolute import path.

### FFL002: no-star-imports

Family: `layers`

star imports hide names from dependency-boundary analysis

Remediation: Import each required name explicitly.

### FFL101: no-sibling-package-internals

Family: `layers`

subpackage code must not import sibling internals

Remediation: Publish the dependency through the owning sibling's main/ entry or role files.

### FFL102: no-cross-package-internals

Family: `layers`

cross-package imports must use public surfaces, not helpers or internals

Remediation: Import from classes, models, types, constants, exceptions, or a thin main/ entry.

### FFL103: no-internal-public-surface-imports

Family: `layers`

internal code must import from the owning module, not the bare package

Remediation: Import from the concrete owning module below the package surface.

### FFL104: no-cross-domain-private-main-imports

Family: `layers`

domain-private main entries may only be imported within their owning domain

Remediation: Remove the leading underscore to publish the main entry, or route the caller through a public main entry owned by the target domain.

### FFL105: public-main-entry-external-use

Family: `layers`

public main entries must have an importer outside their owning domain

Remediation: Prefix the entry module filename with '_' until another domain or tooling imports it.

### FFL110: no-cross-file-use-of-helper-private-class

Family: `layers`

helper-private classes are file-local details; move shared classes to classes/

Remediation: If another module needs this class, move it to the owning classes/ package.

### FFL301: no-runtime-imports-from-tooling

Family: `layers`

runtime code must not import from tooling modules

Remediation: Move reusable logic into the runtime package or keep the dependency inside tooling.

### FFN001: validator-must-not-return

Family: `naming`

functions under no-return naming contracts must not return values

Remediation: Remove the meaningful return and raise on invalid input, or rename a value-producing function as a query such as is_valid or get_validation_result.

### FFN002: predicate-must-return-bool

Family: `naming`

predicate names must declare an ordinary boolean result

Remediation: Return bool (or TypeGuard/TypeIs), or rename the function to describe the value it returns, such as read_status or current_status.

### FFN003: value-name-must-return-value

Family: `naming`

value-producing names must not declare a no-value result

Remediation: Return the queried or converted value, or rename the function to describe its side effect, such as initialize_cache or export_json.

### FFN004: iterator-name-must-produce-iterator

Family: `naming`

iterator names must produce an iterator or generator

Remediation: Return an iterator or generator, or rename an eager collection function with a name such as collect_items.

### FFR001: models-only-models

Family: `roles`

models role files may contain only structured runtime models

Remediation: Move functions and non-model declarations to their owning role module.

### FFR002: types-only-types

Family: `roles`

types role files may contain only type-layer declarations

Remediation: Move runtime values and functions out of types.py into their owning runtime role.

### FFR003: constants-only-constants

Family: `roles`

constants role files may contain only assignments and imports

Remediation: Move functions and classes out of constants.py into their owning role module.

### FFR004: exceptions-only-exceptions

Family: `roles`

exceptions role files may contain only custom exceptions

Remediation: Move non-exception declarations out of exceptions.py into their owning role.

### FFR101: model-declaration-outside-models

Family: `roles`

structured runtime models must be defined in the models role

Remediation: Move the dataclass or structured model into models.py or a models/ package.

### FFR102: type-declaration-outside-types

Family: `roles`

type-layer declarations must be defined in the types role

Remediation: Move the protocol, enum, TypedDict, or public type alias into types.py.

### FFR103: constant-outside-constants

Family: `roles`

public uppercase constants must be defined in the constants role

Remediation: Move the public constant into constants.py and import it from there.

### FFR104: exception-declaration-outside-exceptions

Family: `roles`

custom exceptions must be defined in the exceptions role

Remediation: Move the exception class into exceptions.py or an exceptions/ package.

### FFR201: banned-generic-filename

Family: `roles`

generic filenames hide module ownership

Remediation: Rename the module after the domain concept or operation it owns.

### FFR202: helpers-module-name

Family: `roles`

use an _helpers package instead of helpers.py

Remediation: Replace helpers.py with an _helpers/ package of specifically named modules.

### FFR203: classes-module-name

Family: `roles`

use a classes package instead of classes.py

Remediation: Replace classes.py with a classes/ package containing one class per module.

### FFR204: banned-generic-package-name

Family: `roles`

runtime package directories must identify an owner

Remediation: Rename the package after the business domain or technical capability it owns.

### FFR205: helpers-classes-file-private

Family: `roles`

plain classes in _helpers modules must be file-private

Remediation: Prefix a file-local helper class with _, or move a shared class into classes/.

### FFR301: helpers-package-layout

Family: `roles`

_helpers/ packages must use bounded flat-or-grouped containers

Remediation: Keep _helpers/ flat or group every module into bounded shallow buckets; do not mix modules and Python-containing buckets in one container.

### FFR302: main-package-layout

Family: `roles`

main/ packages must use bounded flat-or-grouped orchestration containers

Remediation: Keep main/ flat or group every entry into bounded shallow buckets; do not mix modules and Python-containing buckets in one container.

### FFR303: helpers-reserved-role-filenames

Family: `roles`

_helpers/ packages must not contain reserved role filenames

Remediation: Rename the helper module after its specific operation, or move role-owned declarations to the corresponding sibling models, types, constants, or exceptions role.

### FFR304: nested-direct-modules

Family: `roles`

nested runtime packages may contain only role-oriented direct modules

Remediation: Move additional implementation modules under the package's _helpers/ boundary.

### FFR305: nested-direct-subpackages

Family: `roles`

nested runtime packages must use explicit role boundaries

Remediation: Move feature subpackages under _helpers/ or use a supported role such as main/ or classes/.

### FFR306: top-level-domain-shape

Family: `roles`

top-level domains must be either role leaves or subdomain branches

Remediation: Keep direct role content in a leaf domain, or move it into a named subdomain when the domain contains subdomains.

### FFR307: top-level-direct-modules

Family: `roles`

top-level domains must not contain ad hoc direct modules

Remediation: Move the module under a direct role boundary or into an owning named subdomain.

### FFR308: shared-domain-prefix

Family: `roles`

sibling domains must not encode one parent domain through a shared name prefix

Remediation: Create one parent domain from the shared prefix and move each remaining suffix beneath it as a named subdomain.

### FFR309: leaf-main-boundary

Family: `roles`

leaf runtime domains and subdomains must expose meaningful behavior through main/

Remediation: Add a focused main/ entry module only when the leaf owns behavior; otherwise move passive declarations into the closest domain or subdomain whose main/ behavior owns and uses them.

### FFR401: entry-module-shape

Family: `roles`

main/ entry modules must expose one focused public function

Remediation: Keep only imports, one public entry function, and at most two small private glue functions; move phase logic to _helpers/.

### FFR402: init-module-empty

Family: `roles`

nested __init__.py files must be empty or docstring-only

Remediation: Remove runtime declarations and import from the concrete owning module instead.

### FFR403: no-reexport-shim

Family: `roles`

internal modules must not exist only to re-export imports

Remediation: Import the implementation module directly or expose a deliberate API through an approved public surface.

### FFR404: no-internal-helper-exports

Family: `roles`

_helpers/ modules must not publish an __all__ surface

Remediation: Keep _helpers/ internal and expose public behavior through main/, classes/, models, types, constants, or exceptions.

### FFR405: main-entry-name-collision

Family: `roles`

main/ cannot define a module and package with the same entry name

Remediation: Choose either the flat entry module or the same-named package and remove the competing surface.

### FFR406: public-surface-shape

Family: `roles`

root package surfaces may contain only imports and one __all__ declaration

Remediation: Move runtime behavior into an owning module and keep the root __init__.py as a deliberate import surface.

### FFR501: classes-one-class-per-module

Family: `roles`

classes/ modules must define exactly one top-level class

Remediation: Split additional classes into separately named modules under classes/.

### FFR502: helpers-package-shape

Family: `roles`

_helpers/ packages must contain no main.py orchestration entrypoints

Remediation: Move main.py orchestration into the sibling main/ role; helper depth is enforced by FFR301.

### FFR503: private-definition-ordering

Family: `roles`

private constants and dataclasses must appear before top-level functions

Remediation: Move private module declarations above the first function so readers see module state before behavior.

### FFR601: source-file-line-count

Family: `roles`

source files must stay below the configured line limit

Remediation: Split the file by a cohesive role or concern instead of extracting arbitrary numbered fragments.

### FFR701: tooling-entrypoint-shape

Family: `roles`

direct scripts must remain focused command adapters

Remediation: Keep one public main(), optional private _parse_args() and _build_parser(), and move implementation into a scripts/<tool>/main/ entry.

### FFR702: tooling-entrypoint-delegation

Family: `roles`

direct scripts must delegate to an imported main/ entrypoint

Remediation: Import a typed entry function from a runtime or scripts/<tool>/main/ module and return its result from main().

### FFR703: tooling-entrypoint-line-count

Family: `roles`

direct scripts must stay below the configured line limit

Remediation: Move command implementation into a named tooling or runtime package.

### FFR704: rules-role-content

Family: `roles`

tooling rules/ modules may contain only decorated rule declarations

Remediation: Keep imports and @rule functions here; move supporting implementation into _helpers/, classes/, models.py, types.py, constants.py, or exceptions.py.

### FFR705: tooling-package-layout

Family: `roles`

tool packages must organize implementation through explicit roles

Remediation: Use main/, _helpers/, classes/, rules/, models.py, types.py, constants.py, or exceptions.py directly beneath scripts/<tool>/.

### FFR706: descriptive-rule-module-names

Family: `roles`

rule module filenames must describe their policy rather than repeat one rule code

Remediation: Rename the module after the policy or rule family it implements, using a name such as conditional_test_flow.py instead of fft104.py.

### FFR707: custom-rule-test-coverage

Family: `roles`

configured custom rules must have statically declared public-harness cases

Remediation: Add statically visible RuleCase construction passed to evaluate_rule for each custom rule. When FFT413 is active, parametrize with a local _test_types.py dataclass and convert it to RuleCase inside the test.

### FFS001: too-many-statements

Family: `shape`

main functions must stay phase-shaped and below the statement limit

Remediation: Extract cohesive phases into helpers that return explicit result models.

### FFS002: too-many-distinct-calls

Family: `shape`

main functions must not coordinate too many distinct callees

Remediation: Group related work into named phase helpers and keep main/ as a short ordered flow.

### FFS003: too-many-locals

Family: `shape`

main functions must not juggle too many local variables

Remediation: Let each extracted phase own its intermediates and return one structured result.

### FFS010: max-arguments

Family: `shape`

functions must stay below the configured argument limit

Remediation: Reduce the function's responsibility or group cohesive inputs into a typed model.

### FFS011: max-statements-global

Family: `shape`

functions must stay below the global statement limit

Remediation: Split the function at a meaningful phase boundary with explicit inputs and outputs.

### FFS101: meaningful-project-result-discarded

Family: `shape`

main orchestrators must consume meaningful project-local call results

Remediation: Assign, return, or explicitly discard the phase result with _ = call(...).

### FFS110: default-mutation-return

Family: `shape`

functions that mutate parameters must return every mutated parameter

Remediation: Return each mutated parameter explicitly, or avoid parameter mutation and return a new value.

### FFS120: keyword-only-arguments

Family: `shape`

functions beyond the parameter threshold must be entirely keyword-only

Remediation: Insert * before the first non-receiver parameter so every call argument names its meaning.

### FFS130: no-outer-state-mutation

Family: `shape`

functions must not mutate module-global or closure-captured state

Remediation: Pass state explicitly and return the updated value instead of mutating outer scope.

### FFS131: no-complex-comprehensions

Family: `shape`

nested or multi-generator comprehensions hide control flow and data shapes

Remediation: Extract a named helper when the transformation has a coherent purpose. For one-off local logic, use simple statements with named intermediate values instead of nested comprehension control flow.

### FFS201: mutable-result-model

Family: `shape`

dataclass result models must be frozen

Remediation: Declare the shared result model with @dataclass(frozen=True).

### FFT001: test-layout

Family: `tests`

tests must live under a configured test root and supported scope

Remediation: Move the test beneath a configured test root and one of the configured test_scopes.

### FFT002: test-scope

Family: `tests`

test scope must be one of the configured test scopes

Remediation: Move the test beneath a configured test root and one of the configured test_scopes.

### FFT003: test-mirrored-root

Family: `tests`

test directories must mirror a configured runtime or tooling root

Remediation: Mirror the complete configured source or tooling path beneath the test scope.

### FFT004: src-mirror-depth

Family: `tests`

runtime tests must include an area beneath the configured source root

Remediation: Move the test beneath the package and source area it exercises.

### FFT005: src-package-exists

Family: `tests`

runtime tests must mirror a configured source package

Remediation: Correct the mirrored package name or move the test to the package it exercises.

### FFT006: src-area-exists

Family: `tests`

runtime tests must mirror an existing source package area

Remediation: Correct the mirrored area path so it matches the runtime module location.

### FFT007: scripts-mirror-depth

Family: `tests`

tooling tests must include an area beneath the configured tooling root

Remediation: Move the test beneath the configured tooling area it exercises.

### FFT008: scripts-area-exists

Family: `tests`

tooling tests must mirror an existing configured tooling area

Remediation: Correct the mirrored area path so it matches the tooling location.

### FFT101: init-module-empty

Family: `tests`

test package __init__.py files must be empty or docstring-only

Remediation: Remove runtime declarations from __init__.py and import them from their owning module.

### FFT102: absolute-imports

Family: `tests`

tests must use absolute imports

Remediation: Replace the relative import with the full tests or application package path.

### FFT103: no-top-level-helpers

Family: `tests`

test modules may contain only tests, imports, and declarations

Remediation: Move reusable functions into the local helpers.py module.

### FFT104: no-if-in-tests

Family: `tests`

tests and local test helpers must not contain conditional control flow

Remediation: Use parametrized cases when setup and assertions remain branch-free; otherwise split the behavior into separate test functions. Keep local test helpers deterministic with per-variant functions or dataclass-driven case data.

### FFT105: private-constant-order

Family: `tests`

private test constants must appear before test functions

Remediation: Move the private constant above the first test so module setup is visible before behavior.

### FFT106: no-complex-comprehensions

Family: `tests`

nested or multi-generator comprehensions hide control flow and data shapes

Remediation: Extract a named helper when the transformation has a coherent purpose. For one-off local logic, use simple statements with named intermediate values instead of nested comprehension control flow.

### FFT201: test-types-description

Family: `tests`

test-case dataclasses must define a description field

Remediation: Add description: str so parametrized cases explain the behavior they represent.

### FFT202: test-types-expected-field

Family: `tests`

test-case dataclasses must define at least one expected_ field

Remediation: Name expected outcomes with an expected_ prefix and assert against them in the test.

### FFT203: local-test-types-import

Family: `tests`

tests must import test-case types from their local _test_types.py

Remediation: Move the dataclass beside the test and import it through the mirrored absolute path.

### FFT204: local-test-types-file

Family: `tests`

test directories must provide a local _test_types.py

Remediation: Create _test_types.py beside the test. Custom-rule tests should define a local wrapper dataclass there rather than parametrizing directly with RuleCase.

### FFT301: test-file-name

Family: `tests`

test modules must use a test_ filename

Remediation: Rename the module to test_<behavior>.py.

### FFT302: test-function-name

Family: `tests`

test functions must use test_given_<state>_when_<action>_then_<outcome>

Remediation: Rename the test so its precondition, action, and expected behavior are explicit.

### FFT401: dataclass-parametrize

Family: `tests`

tests must use dataclass-backed pytest parameterization

Remediation: Add @pytest.mark.parametrize with local test_case dataclass instances.

### FFT402: accepts-test-case

Family: `tests`

parametrized tests must accept a test_case argument

Remediation: Name the parameter test_case and read inputs and expectations from that object.

### FFT403: test-case-annotation

Family: `tests`

test_case parameters must use a local test-case dataclass annotation

Remediation: Annotate test_case with a dataclass imported from the local _test_types.py.

### FFT404: expected-field-assertion

Family: `tests`

tests must assert against an expected_ field from test_case

Remediation: Store the expected outcome on test_case and reference it in a behavior assertion.

### FFT405: parametrize-arguments

Family: `tests`

pytest parametrize decorators must define parameter names and values

Remediation: Pass both the parameter-name string and the case sequence to parametrize.

### FFT406: parametrize-test-case

Family: `tests`

pytest parametrize must expose cases through the test_case parameter

Remediation: Use "test_case" as the parametrize parameter name.

### FFT407: parametrize-ids

Family: `tests`

pytest parametrize decorators must define readable case ids

Remediation: Set ids to the case descriptions, normally with ids=lambda case: case.description.

### FFT408: inline-parametrize-values

Family: `tests`

pytest parametrize values must be a visible list, tuple, or local comprehension

Remediation: Inline the case sequence in @pytest.mark.parametrize so its cases are visible beside the test.

### FFT411: nonempty-parametrize-values

Family: `tests`

pytest parametrize case sequences must not be empty

Remediation: Add at least one behavior case or remove the test until a real case exists.

### FFT412: no-dict-test-cases

Family: `tests`

pytest cases must use typed dataclasses instead of dictionaries

Remediation: Define a local frozen test-case dataclass and construct one instance per case.

### FFT413: local-test-case-constructors

Family: `tests`

pytest cases must construct dataclasses from the local _test_types.py

Remediation: Parametrize using a dataclass imported from local _test_types.py. For framework harness inputs such as RuleCase, store their fields in the local dataclass and construct the framework object inside the test.

### FFT414: description-lambda-ids

Family: `tests`

pytest case ids must come from each test case description

Remediation: Use ids=lambda case: case.description so failures identify the behavior clearly.

### XSTB001: adapter-package-ownership

Family: `custom`

modules must use the active adapter package boundaries

Remediation: Depend on the neutral streambuild.adapter contract from compiler modules, and replace retired streambuild.clickhouse or streambuild.integrations.clickhouse imports with their streambuild.adapters.clickhouse owners.

### XSTB002: warehouse-driver-ownership

Family: `custom`

only the ClickHouse adapter may import the ClickHouse driver

Remediation: Move driver access and driver-exception translation into src/streambuild/adapters/clickhouse/ and depend on neutral adapter exceptions.

### XSTB003: sql-analysis-import-ownership

Family: `custom`

SQL analysis engines must remain inside their migration boundary

Remediation: Import Polyglot only from src/streambuild/compiler/sql_analysis/, and do not reintroduce a removed SQL analysis engine.

### XSTB004: workflow-mutation-gateway

Family: `custom`

warehouse mutations must pass through the workflow gateway

Remediation: Assemble exact SQL in an approved workflow assembler and execute it only through executor/workflow/main/_execute_warehouse_workflow.py.

### XSTB005: published-workflow-capability

Family: `custom`

build execution requires the artifact publication capability

Remediation: Construct PublishedBuildWorkflow only in workflow artifact publication and pass that capability to execute_build_workflow.

### XSTB006: workflow-consumer-purity

Family: `custom`

workflow consumers must not derive SQL or execution order

Remediation: Move rendering, planning, ordering, and statement construction into an approved command workflow assembler.

### XSTB007: workflow-statement-ownership

Family: `custom`

workflow statements must be constructed by approved command assemblers

Remediation: Construct WarehouseStatement values only in a path listed by WORKFLOW_ASSEMBLER_PATHS.

### XSTB008: observability-non-authority

Family: `custom`

planner and lifecycle code must not read non-authoritative observability history

Remediation: Use authoritative ownership, replay, deployment, publication, object-state, and live catalog evidence for lifecycle decisions; reserve invocation and node-result history for UI.

## Warning Rules

None.
