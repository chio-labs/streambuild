from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from streambuild.spec.models import Project


@dataclass(frozen=True)
class CliEntrypointHandlers:
    run_discover: Callable[..., int]
    run_compile: Callable[..., int]
    run_test: Callable[..., int]
    run_audit: Callable[..., int]
    run_plan: Callable[..., int]
    run_backfill: Callable[..., int]
    run_audit_backfill: Callable[..., int]
    run_publish: Callable[..., int]
    run_reconcile: Callable[..., int]
    run_janitor: Callable[..., int]
    run_doctor: Callable[..., int]
    run_repair_active_view: Callable[..., int]


@dataclass(frozen=True)
class ResolvedClickHouseConnection:
    host: str
    port: int
    username: str
    password: str


@dataclass(frozen=True)
class ResolvedCliProjectConfig:
    connection: ResolvedClickHouseConnection | None
    default_database: str | None
    project: Project | None
