from dataclasses import dataclass


@dataclass(frozen=True)
class AdminCliTestCase:
    description: str
    expected_username: str
