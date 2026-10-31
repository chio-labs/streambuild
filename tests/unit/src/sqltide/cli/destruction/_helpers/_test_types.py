from dataclasses import dataclass


@dataclass(frozen=True)
class DestructionRenderingTestCase:
    description: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DestructionChallengeInputTestCase:
    description: str
    response: str
    expected_responses: tuple[str, ...]
