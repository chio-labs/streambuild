"""CLI presentation constants."""

ANSI_RESET: str = "\033[0m"
ANSI_BOLD: str = "\033[1m"
ANSI_DIM: str = "\033[2m"
ANSI_BLUE: str = "\033[34m"
ANSI_GREEN: str = "\033[32m"
ANSI_YELLOW: str = "\033[33m"
ANSI_RED: str = "\033[31m"
NOT_AVAILABLE: str = "n/a"
UTC_SUFFIX: str = "Z"
TRUTHY_ENV_VALUES: frozenset[str] = frozenset({"1", "true", "yes"})
