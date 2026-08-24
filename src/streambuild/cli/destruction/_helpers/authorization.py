"""Standalone CLI destruction authorization."""

from uuid import UUID

from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.constants import ADMIN_ROLE
from streambuild.auth.models import UserAccount
from streambuild.cli.entry.exceptions import CliUserError


def require_destruction_admin(*, store: ControlStore, os_username: str) -> UserAccount:
    """Resolve an active built-in administrator from the OS username."""

    account: UserAccount | None = store.get_user_by_username(username=os_username)
    if account is None:
        raise CliUserError(
            f"OS user '{os_username}' is not registered in the StreamBuild control store"
        )
    if not account.is_active:
        raise CliUserError(f"StreamBuild account '{account.username}' is inactive")
    if ADMIN_ROLE not in account.roles:
        raise CliUserError(
            f"StreamBuild account '{account.username}' requires the built-in '{ADMIN_ROLE}' role"
        )
    return account


def require_same_destruction_admin(
    *, store: ControlStore, os_username: str, expected_user_id: UUID
) -> UserAccount:
    """Reauthorize the plan creator without accepting same-name account replacement."""

    account: UserAccount = require_destruction_admin(store=store, os_username=os_username)
    if account.user_id != expected_user_id:
        raise CliUserError(
            f"StreamBuild account '{account.username}' changed identity during destruction review"
        )
    return account
