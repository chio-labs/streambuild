from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from streambuild.auth.classes.authentication_service import AuthenticationService
from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.main.register_authentication_routes import register_authentication_routes
from streambuild.auth.models import AuthSettings


def build_control_store(*, tmp_path: Path) -> ControlStore:
    return ControlStore(url=f"sqlite:///{tmp_path / 'control.db'}")


def build_auth_client(*, settings: AuthSettings, store: ControlStore) -> TestClient:
    app: FastAPI = FastAPI()
    register_authentication_routes(
        app=app,
        service=AuthenticationService(settings=settings, store=store),
    )

    @app.api_route("/api/protected", methods=["GET", "POST"])
    def protected() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)
