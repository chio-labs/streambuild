from dataclasses import dataclass


@dataclass(frozen=True)
class PublishCapabilityRejectionTestCase:
    description: str
    expected_error_fragment: str
