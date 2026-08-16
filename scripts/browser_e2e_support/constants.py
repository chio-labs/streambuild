"""Stable reverse-proxy test support constants."""

PROXY_STRIPPED_REQUEST_HEADERS: frozenset[str] = frozenset(
    {"host", "x-mustard-user", "content-length"}
)
PROXY_STRIPPED_RESPONSE_HEADERS: frozenset[str] = frozenset(
    {"connection", "content-length", "keep-alive", "proxy-authenticate", "transfer-encoding"}
)
