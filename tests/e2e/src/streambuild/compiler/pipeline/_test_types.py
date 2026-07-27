from dataclasses import dataclass


@dataclass(frozen=True)
class CompilePerformanceTestCase:
    description: str
    model_count: int
    expected_max_seconds: float
