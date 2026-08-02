from dataclasses import dataclass

from fensu import RuleFile


@dataclass(frozen=True)
class CustomRuleTestCase:
    description: str
    path: str
    source: str
    expected_fault_count: int
    expected_dependency_count: int = 0
    files: tuple[RuleFile, ...] = ()
    scope: str = "root"
    scope_root: str | None = "src/streambuild"
