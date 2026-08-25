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
- Run targeted tests for changed behavior plus fast static checks locally. CI is the authoritative
  full-suite gate; do not run the complete test matrix locally unless explicitly requested or
  needed to diagnose a failure.
- Review the complete local diff against the target branch and resolve findings before pushing.
- Do not push partial or overlapping branches merely to start CI.
- Once consolidated work is ready, push once and open one ready pull request so CI and configured
  auto-merge can complete delivery.
- Do not wait interactively for CI with commands such as `gh run watch`; rely on asynchronous CI
  completion and continue only independent local work.
- Push follow-up commits only for CI failures or correctness findings that could not reasonably
  have been found before the first push.
- Use separate pull requests only for independently releasable changes, intentionally different
  delivery timing, or explicit user instruction.

The project interpreter is pinned by `.python-version`; do not substitute a
cached prerelease interpreter when running verification.
