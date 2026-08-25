# Local Agent Notes

## uv Lockfile

This machine's default `uv` is currently `0.7.5`, while this repository requires
uv `0.12.3` or a compatible `0.12.x` release. Running lock-aware commands with
the default binary is rejected before it can downgrade the lock. CI runs
`uv sync --locked --all-groups`, so stale project metadata or an old lock
revision will fail before tests start.

- Use modern uv for dependency and lockfile operations:
  `uvx --from uv@0.12.3 uv lock`
- Reproduce CI's locked sync with:
  `uvx --from uv@0.12.3 uv sync --locked --all-groups`
- After syncing, run tools directly from `.venv/bin/` when practical so the
  old system uv cannot rewrite the lockfile.
- Keep the editable `streambuild` package version in `uv.lock` equal to the
  version in `pyproject.toml`.
- Never restore `uv.lock` merely because the local old uv changed it. First
  regenerate it with modern uv and inspect the resulting diff.
- Before committing, confirm `uvx --from uv@0.12.3 uv sync --locked --all-groups`
  succeeds and that `git diff -- uv.lock` contains only intentional changes.

## Delivery Workflow

- Consolidate related work into one delivery branch and one pull request, even when it covers
  multiple linked issues.
- Local commits are checkpoints and do not trigger CI. Complete all related implementation and
  review before the first push.
- Use targeted tests while developing, then run the full unit and integration suites locally before
  pushing broad planner, executor, adapter, API, or UI behavior changes. CI is an independent gate,
  not a substitute for locally reproducible coverage; document any suite that cannot run locally.
- Review the complete local diff against the target branch and resolve findings before pushing.
- Do not push partial or overlapping branches merely to start CI.
- Once consolidated work is ready, push once and open one ready pull request so CI and configured
  auto-merge can complete delivery.
- Monitor CI after every push and follow it through completion. Keep independent work moving while
  checks run, but watch in the foreground when no other useful work remains and address failures
  before considering delivery complete.
- Push follow-up commits only for CI failures or correctness findings that could not reasonably
  have been found before the first push.
- Use separate pull requests only for independently releasable changes, intentionally different
  delivery timing, or explicit user instruction.

## Review Discipline

- Treat review findings as hypotheses to validate against the supported product contract, ownership
  boundary, and realistic execution paths before changing code.
- Prioritize concrete correctness, authorization, data-loss, and mutation risks within systems the
  project manages. Distinguish those from unsupported external misuse or purely theoretical states.
- Keep fixes proportional. Prefer the smallest change that closes the demonstrated risk; do not add
  cross-system scans, new adapter contracts, or broad defensive machinery without a product
  requirement or evidence that the project owns that boundary.
- Classify findings as in-scope blockers, related follow-ups, or unrelated observations. Do not
  expand the active change merely because a reviewer or subagent found something worth considering.
- For non-blocking or out-of-scope findings, recommend a focused Linear issue for separate
  investigation instead of fixing them opportunistically. Create the issue only when authorized by
  the user or the active workflow, and link it from the current work when it affects residual risk.
- Ask for a short product decision when a proposed safeguard would expand supported behavior,
  permissions, operational cost, or system ownership.

The project interpreter is pinned by `.python-version`; do not substitute a
cached prerelease interpreter when running verification.
