from dataclasses import dataclass


@dataclass(frozen=True)
class FreshLandingOffsetResetE2ETestCase:
    description: str
    payload: bytes
    committed_offset: int
    expected_replayed_offsets: tuple[int, ...]
