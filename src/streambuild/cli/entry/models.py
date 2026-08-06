from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from streambuild.adapter.classes.adapter import Adapter
from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterConnectionConfig
from streambuild.compiler.discovery.models import LoadedProject, RawConnectionConfig


@dataclass(frozen=True)
class CliEntrypointHandlers:
    run_discover: Callable[..., int]
    run_compile: Callable[..., int]
    run_test: Callable[..., int]
    run_audit: Callable[..., int]
    run_plan: Callable[..., int]
    run_build: Callable[..., int]
    run_deployment_list: Callable[..., int]
    run_deployment_show: Callable[..., int]
    run_deployment_audit: Callable[..., int]
    run_deployment_promote: Callable[..., int]
    run_reconcile: Callable[..., int]
    run_janitor: Callable[..., int]
    run_doctor: Callable[..., int]
    run_repair_active_view: Callable[..., int]
    run_dev: Callable[..., int]


@dataclass(frozen=True, repr=False)
class ResolvedCliProjectConfig:
    connection: AdapterConnectionConfig | None
    default_database: str | None
    adapter_name: str
    loaded_project: LoadedProject | None
    raw_connection: RawConnectionConfig | None = None
    variables: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, repr=False)
class CliConnectionOptions:
    host: str | None
    port: int | None
    username: str | None
    password: str | None
    project_connection: AdapterConnectionConfig | None
    raw_project_connection: RawConnectionConfig | None = None
    variables: tuple[tuple[str, object], ...] = ()
    environment: Mapping[str, str] | None = None


@dataclass(frozen=True, repr=False)
class ResolvedCliInvocation:
    args: argparse.Namespace
    project_dir: Path | None
    pipelines_root: Path | None
    database: str | None
    adapter: Adapter
    loaded_project: LoadedProject | None
    connection: CliConnectionOptions


@dataclass(frozen=True)
class ResolvedInvocationConnection:
    connection: AdapterConnection | None
    close_after_command: bool
