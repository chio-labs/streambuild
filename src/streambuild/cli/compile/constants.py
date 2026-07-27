"""Compile artifact constants."""

RESERVED_TARGET_OWNER_NAMES: frozenset[str] = frozenset(
    {"compiled", "run", "manifest.json", "streambuild_dag.json"}
)
ARTIFACTS_MANIFEST_FIELD: str = "artifacts"
BROKER_USERINFO_SEPARATOR: str = "@"
PARENT_PATH_SEGMENT: str = ".."
UNSAFE_ARTIFACT_PATH_SEGMENTS: frozenset[str] = frozenset({".", PARENT_PATH_SEGMENT})
ARTIFACT_PATH_SEPARATORS: tuple[str, ...] = ("/", "\\")
SENSITIVE_SOURCE_SETTING_FRAGMENTS: tuple[str, ...] = (
    "credential",
    "password",
    "private_key",
    "sasl",
    "secret",
    "token",
)
