from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from streambuild.adapter.classes.adapter import Adapter
from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterConnectionConfig
from streambuild.compiler.discovery.models import Project


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
class ResolvedCliProjectConfig:
    connection: AdapterConnectionConfig | None
    default_database: str | None
    adapter_name: str
    project: Project | None


@dataclass(frozen=True, repr=False)
class CliConnectionOptions:
    host: str | None
    port: int | None
    username: str | None
    password: str | None
    project_connection: AdapterConnectionConfig | None


@dataclass(frozen=True)
class ResolvedCliInvocation:
    args: argparse.Namespace
    project_dir: Path | None
    pipelines_root: Path | None
    database: str | None
    adapter: Adapter
    connection: CliConnectionOptions


@dataclass(frozen=True)
class ResolvedInvocationConnection:
    connection: AdapterConnection | None
    close_after_command: bool
