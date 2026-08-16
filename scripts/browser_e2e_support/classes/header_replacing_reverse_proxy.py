"""Loopback reverse proxy for trusted-header browser coverage."""

from http.client import HTTPConnection, HTTPResponse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from scripts.browser_e2e_support.constants import (
    PROXY_STRIPPED_REQUEST_HEADERS,
    PROXY_STRIPPED_RESPONSE_HEADERS,
)


class HeaderReplacingReverseProxy:
    """Strip incoming identity claims and inject one proxy-authenticated user."""

    def __init__(self, *, upstream_port: int, username: str) -> None:
        handler: type[BaseHTTPRequestHandler] = _proxy_handler(
            upstream_port=upstream_port, username=username
        )
        self._server: ThreadingHTTPServer = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread: Thread = Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _proxy_handler(*, upstream_port: int, username: str) -> type[BaseHTTPRequestHandler]:
    class ProxyHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            self._forward()

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            self._forward()

        def _forward(self) -> None:
            body_length: int = int(self.headers.get("content-length", "0"))
            body: bytes | None = self.rfile.read(body_length) if body_length else None
            headers: dict[str, str] = {
                name: value
                for name, value in self.headers.items()
                if name.casefold() not in PROXY_STRIPPED_REQUEST_HEADERS
            }
            headers["Host"] = f"127.0.0.1:{upstream_port}"
            headers["X-Mustard-User"] = username
            upstream: HTTPConnection = HTTPConnection("127.0.0.1", upstream_port, timeout=15)
            try:
                upstream.request(self.command, self.path, body=body, headers=headers)
                response: HTTPResponse = upstream.getresponse()
                payload: bytes = response.read()
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.casefold() not in PROXY_STRIPPED_RESPONSE_HEADERS:
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            finally:
                upstream.close()

    return ProxyHandler
