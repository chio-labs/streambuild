"""Run operator-only account bootstrap and recovery commands."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path

from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.exceptions import ControlStoreError
from streambuild.auth.main.default_control_store_url import default_control_store_url
from streambuild.cli.admin._helpers.command_dispatch import dispatch_admin_command
from streambuild.cli.admin.constants import CONTROL_STORE_ENV_VAR
from streambuild.cli.entry.exceptions import CliUserError


def run_admin_command(
    *,
    args: argparse.Namespace,
    environment: Mapping[str, str],
    working_directory: Path,
) -> int:
    """Execute one account operation without opening a warehouse connection."""

    project_dir_value: Path | None = getattr(args, "project_dir", None)
    project_dir: Path = (
        working_directory
        if project_dir_value is None
        else project_dir_value
        if project_dir_value.is_absolute()
        else working_directory / project_dir_value
    )
    url: str = (
        getattr(args, "control_store_url", None)
        or environment.get(CONTROL_STORE_ENV_VAR)
        or default_control_store_url(project_dir=project_dir)
    )
    try:
        store: ControlStore = ControlStore(url=url)
        try:
            return dispatch_admin_command(args=args, store=store)
        finally:
            store.close()
    except (ControlStoreError, ValueError) as error:
        raise CliUserError(str(error)) from error
