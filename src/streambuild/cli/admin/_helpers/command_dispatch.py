"""Dispatch one parsed account-administration command."""

import argparse

from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.constants import VIEWER_ROLE
from streambuild.auth.models import UserAccount
from streambuild.auth.types import AuthenticationSource
from streambuild.cli.admin._helpers.password_input import read_password
from streambuild.cli.admin.types import AdminCommand
from streambuild.cli.entry.exceptions import CliUserError


def dispatch_admin_command(*, args: argparse.Namespace, store: ControlStore) -> int:
    """Execute one parsed command against an open control store."""

    command: AdminCommand = AdminCommand(args.admin_command)
    if command == AdminCommand.MIGRATE:
        store.bootstrap()
        print("StreamBuild account schema is ready")
        return 0
    if command == AdminCommand.CREATE_USER:
        return _create_user(args=args, store=store)
    account: UserAccount | None = store.get_user_by_username(username=args.username)
    if account is None:
        raise CliUserError(f"User '{args.username}' was not found")
    return _mutate_user(command=command, args=args, store=store, account=account)


def _create_user(*, args: argparse.Namespace, store: ControlStore) -> int:
    source: AuthenticationSource = AuthenticationSource(args.authentication_source)
    password: str | None = read_password() if source == AuthenticationSource.PASSWORD else None
    account: UserAccount = store.create_user(
        username=args.username,
        display_name=args.display_name,
        email=args.email,
        password=password,
        authentication_source=(source if source == AuthenticationSource.TRUSTED_PROXY else None),
        external_subject=(
            args.username.strip().casefold()
            if source == AuthenticationSource.TRUSTED_PROXY
            else None
        ),
        roles=tuple(args.role or (VIEWER_ROLE,)),
    )
    print(f"Created user {account.username} ({account.user_id})")
    return 0


def _mutate_user(
    *,
    command: AdminCommand,
    args: argparse.Namespace,
    store: ControlStore,
    account: UserAccount,
) -> int:
    if command == AdminCommand.GRANT_ROLE:
        updated: UserAccount = store.grant_role(
            user_id=account.user_id, role_name=args.role, actor_user_id=None
        )
        print(f"Granted {args.role} to {updated.username}")
        return 0
    if command == AdminCommand.REVOKE_ROLE:
        updated = store.revoke_role(
            user_id=account.user_id, role_name=args.role, actor_user_id=None
        )
        print(f"Revoked {args.role} from {updated.username}")
        return 0
    if command in {AdminCommand.ENABLE_USER, AdminCommand.DISABLE_USER}:
        enabled: bool = command == AdminCommand.ENABLE_USER
        updated = store.set_user_active(
            user_id=account.user_id, is_active=enabled, actor_user_id=None
        )
        print(f"{'Enabled' if enabled else 'Disabled'} {updated.username}")
        return 0
    if command == AdminCommand.RESET_PASSWORD:
        store.reset_password(
            user_id=account.user_id,
            password=read_password(),
            actor_user_id=None,
        )
        print(f"Reset password for {account.username}")
        return 0
    raise CliUserError(f"Unknown admin command '{command}'")
