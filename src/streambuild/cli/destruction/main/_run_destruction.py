"""Plan, review, challenge, and execute one CLI destruction command."""

from __future__ import annotations

import getpass

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.exceptions import ControlStoreError
from streambuild.auth.models import UserAccount
from streambuild.cli.destruction._helpers.authorization import require_destruction_admin
from streambuild.cli.destruction._helpers.execution import run_authorized_destruction
from streambuild.cli.destruction.models import DestructionCommandOptions
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject


def run_destruction(
    *,
    options: DestructionCommandOptions,
    client: AdapterConnection,
    observation_client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Authorize and execute an interactive, single-use destruction plan."""

    try:
        control_store: ControlStore = ControlStore(url=options.control_store_url)
    except ControlStoreError as error:
        raise CliUserError(str(error)) from error
    try:
        os_username: str = getpass.getuser()
        account: UserAccount = require_destruction_admin(
            store=control_store,
            os_username=os_username,
        )
        return run_authorized_destruction(
            options=options,
            account=account,
            control_store=control_store,
            os_username=os_username,
            client=client,
            observation_client=observation_client,
            loaded_project=loaded_project,
            adapter_profile=adapter_profile,
        )
    except ControlStoreError as error:
        raise CliUserError(str(error)) from error
    finally:
        control_store.close()
