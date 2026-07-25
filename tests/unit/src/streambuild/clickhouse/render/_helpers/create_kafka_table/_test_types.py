from dataclasses import dataclass


@dataclass(frozen=True)
class RenderCreateKafkaTableDdlTestCase:
    description: str
    extra_settings: dict[str, str] | None
    expected_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]
