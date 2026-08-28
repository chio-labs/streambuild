from dataclasses import dataclass


@dataclass(frozen=True)
class ManifestBuildTestCase:
    description: str
    expected_pipelines: tuple[str, ...]


@dataclass(frozen=True)
class ManifestFingerprintTestCase:
    description: str
    expected_equal: bool


@dataclass(frozen=True)
class SharedSourceManifestTestCase:
    description: str
    expected_pipeline_names: frozenset[str]
