"""Construct authentication services owned by one dev-server application."""

from pathlib import Path

from streambuild.auth.classes.authentication_service import AuthenticationService
from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.main.default_control_store_url import default_control_store_url
from streambuild.auth.models import AuthSettings
from streambuild.auth.types import AuthenticationMode


def build_authentication_runtime(
    *,
    project_dir: Path,
    auth_settings: AuthSettings | None,
    control_store: ControlStore | None,
) -> tuple[AuthenticationService, ControlStore, bool]:
    """Build authentication services and report control-store ownership."""

    effective_settings: AuthSettings = auth_settings or AuthSettings(
        mode=AuthenticationMode.DISABLED,
        control_store_url=default_control_store_url(project_dir=project_dir),
    )
    owns_control_store: bool = control_store is None
    active_store: ControlStore = control_store or ControlStore(
        url=effective_settings.control_store_url
    )
    return (
        AuthenticationService(settings=effective_settings, store=active_store),
        active_store,
        owns_control_store,
    )
