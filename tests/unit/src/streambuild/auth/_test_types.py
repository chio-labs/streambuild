from dataclasses import dataclass


@dataclass(frozen=True)
class AuthTestCase:
    description: str
    expected_result: object
