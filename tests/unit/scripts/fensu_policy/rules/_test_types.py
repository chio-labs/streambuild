from dataclasses import dataclass


@dataclass(frozen=True)
class CustomRuleTestCase:
    description: str
    path: str
    source: str
    expected_fault_count: int
    scope: str = "root"
    scope_root: str | None = "src/streambuild"
