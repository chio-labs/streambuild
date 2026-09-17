"""Serve the packaged UI build with an SPA fallback."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.datastructures import MutableHeaders
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from streambuild.dev_server.constants import (
    HTTP_RESPONSE_START_MESSAGE_TYPE,
    STATIC_ASSETS_DIRECTORY_NAME,
)

_INDEX_FILE_NAME: str = "index.html"
_REVALIDATE_CACHE_CONTROL: str = "no-cache, must-revalidate"
_IMMUTABLE_CACHE_CONTROL: str = "public, max-age=31536000, immutable"


class _CacheControlMiddleware:
    def __init__(self, *, app: ASGIApp, cache_control: str) -> None:
        self._app: ASGIApp = app
        self._cache_control: str = cache_control

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_cache_control(message: Message) -> None:
            if message["type"] == HTTP_RESPONSE_START_MESSAGE_TYPE:
                MutableHeaders(scope=message)["Cache-Control"] = self._cache_control
            await send(message)

        await self._app(scope, receive, send_with_cache_control)


def static_assets_root() -> Path:
    """Return the packaged UI build directory; it may not exist in dev checkouts."""

    dev_server_root: Path = Path(__file__).resolve().parents[2]
    return dev_server_root / STATIC_ASSETS_DIRECTORY_NAME


def static_assets_present(*, assets_root: Path) -> bool:
    """Report whether a built UI exists at the packaged assets root."""

    return (assets_root / _INDEX_FILE_NAME).is_file()


def register_static_assets(*, app: FastAPI, assets_root: Path) -> FastAPI:
    """Mount built UI assets and route every non-API path to the SPA shell."""

    index_file: Path = assets_root / _INDEX_FILE_NAME
    if not index_file.is_file():
        return app
    immutable_assets_root: Path = assets_root / "_app" / "immutable"
    if immutable_assets_root.is_dir():
        app.mount(
            "/_app/immutable",
            _CacheControlMiddleware(
                app=StaticFiles(directory=immutable_assets_root),
                cache_control=_IMMUTABLE_CACHE_CONTROL,
            ),
            name="immutable-app-assets",
        )
    app.mount(
        "/_app",
        _CacheControlMiddleware(
            app=StaticFiles(directory=assets_root / "_app"),
            cache_control=_REVALIDATE_CACHE_CONTROL,
        ),
        name="app-assets",
    )

    def read_spa_shell(full_path: str) -> FileResponse:
        candidate: Path = assets_root / full_path
        if full_path and candidate.is_file() and candidate.resolve().is_relative_to(assets_root):
            return FileResponse(candidate, headers={"Cache-Control": _REVALIDATE_CACHE_CONTROL})
        return FileResponse(index_file, headers={"Cache-Control": _REVALIDATE_CACHE_CONTROL})

    app.get("/{full_path:path}")(read_spa_shell)
    return app
