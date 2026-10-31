from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderNameTestCase:
    description: str
    expected_name: str


@dataclass(frozen=True)
class ProviderNameErrorTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ProviderSessionTestCase:
    description: str
    expected_lifecycle_log: tuple[str, ...]


@dataclass(frozen=True)
class ProviderTeardownTestCase:
    description: str
    expected_error_fragment: str
    expected_handler_error_fragment: str | None = None


@dataclass(frozen=True)
class ProviderInjectionTestCase:
    description: str
    expected_injected_count: int = 0
    expected_error_fragment: str | None = None
