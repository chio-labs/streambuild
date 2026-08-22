# Contributing

Keep branches, pull requests, and commits concise enough that the repository history remains useful.

## Branches

Use a typed prefix and lowercase kebab-case description. Include the Linear issue when one exists:

```text
feat/chi-123-description
fix/chi-123-description
perf/description
refactor/description
test/description
docs/description
build/description
ci/description
chore/description
revert/description
```

## Pull Requests

Use a Conventional Commit title because squash merges use the pull request title as the canonical commit:

```text
feat(quality): add audit and test navigation
fix(runs): preserve build history
perf(runs): reduce terminal event payload
ci(release): publish releases automatically
```

Descriptions must remain below 2,000 characters and contain `Why`, `Changes`, and `Verification` sections. State facts, material behavior, and checks actually run. Avoid marketing language, file-by-file narration, generated impact claims, decorative formatting, and full test logs.

Normal pull requests are squash-merged after required checks pass. Intermediate branch commits remain visible on the pull request, while `main` receives one canonical commit and Release Please produces one changelog entry.

## Releases

Release Please derives version bumps and changelog sections from the squash commit:

| Type | Changelog section | Version bump |
| --- | --- | --- |
| `feat` | Features | minor |
| `fix`, `revert` | Bug Fixes | patch |
| `perf` | Performance Improvements | patch |
| `refactor` | Refactoring | patch |
| `build` | Build System | patch |
| `docs` | Documentation | patch |
| `chore` | Maintenance | patch |
| `ci`, `test` | hidden | none by themselves |

Use `!` and a `BREAKING CHANGE:` footer for breaking behavior. StreamBuild blocks automatic `1.0.0` publication, so crossing that boundary remains a manual decision.
