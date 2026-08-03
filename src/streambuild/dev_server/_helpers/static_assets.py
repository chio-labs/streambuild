"""Serve the packaged UI build with an SPA fallback."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from streambuild.dev_server.constants import STATIC_ASSETS_DIRECTORY_NAME

_INDEX_FILE_NAME: str = "index.html"


def static_assets_root() -> Path:
    """Return the packaged UI build directory; it may not exist in dev checkouts."""

    return Path(__file__).resolve().parent.parent / STATIC_ASSETS_DIRECTORY_NAME


def static_assets_present(*, assets_root: Path) -> bool:
    """Report whether a built UI exists at the packaged assets root."""

    return (assets_root / _INDEX_FILE_NAME).is_file()


def register_static_assets(*, app: FastAPI, assets_root: Path) -> FastAPI:
    """Mount built UI assets and route every non-API path to the SPA shell."""

    index_file: Path = assets_root / _INDEX_FILE_NAME
    if not index_file.is_file():
        return app
    app.mount(
        "/_app",
        StaticFiles(directory=assets_root / "_app"),
        name="app-assets",
    )

    def read_spa_shell(full_path: str) -> FileResponse:
        candidate: Path = assets_root / full_path
        if full_path and candidate.is_file() and candidate.resolve().is_relative_to(assets_root):
            return FileResponse(candidate)
        return FileResponse(index_file)

    app.get("/{full_path:path}")(read_spa_shell)
    return app
