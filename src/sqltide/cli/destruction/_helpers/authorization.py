"""Standalone CLI destruction authorization."""

from uuid import UUID

from sqltide.auth.classes.control_store import ControlStore
from sqltide.auth.constants import ADMIN_ROLE
from sqltide.auth.models import UserAccount
from sqltide.cli.entry.exceptions import CliUserError


def require_destruction_admin(*, store: ControlStore, os_username: str) -> UserAccount:
    """Resolve an active built-in administrator from the OS username."""

    account: UserAccount | None = store.get_user_by_username(username=os_username)
    if account is None:
        raise CliUserError(
            f"OS user '{os_username}' is not registered in the SQLTide control store"
        )
    if not account.is_active:
        raise CliUserError(f"SQLTide account '{account.username}' is inactive")
    if ADMIN_ROLE not in account.roles:
        raise CliUserError(
            f"SQLTide account '{account.username}' requires the built-in '{ADMIN_ROLE}' role"
        )
    return account


def require_same_destruction_admin(
    *, store: ControlStore, os_username: str, expected_user_id: UUID
) -> UserAccount:
    """Reauthorize the plan creator without accepting same-name account replacement."""

    account: UserAccount = require_destruction_admin(store=store, os_username=os_username)
    if account.user_id != expected_user_id:
        raise CliUserError(
            f"SQLTide account '{account.username}' changed identity during destruction review"
        )
    return account
