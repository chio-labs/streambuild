"""Build one attached source registry by logical name."""

from streambuild.compiler.discovery._helpers.source_registry import (
    source_registry_by_name as source_registry_by_name_impl,
)
from streambuild.compiler.discovery.models import (
    DiscoveredSourceFile,
    ExternalTableSourceStep,
    KafkaLandingStep,
    PostgresRefreshSourceStep,
)


def source_registry_by_name(
    source_files: tuple[DiscoveredSourceFile, ...],
) -> dict[str, KafkaLandingStep | ExternalTableSourceStep | PostgresRefreshSourceStep]:
    """Return retained sources keyed by their unique logical names."""

    return source_registry_by_name_impl(source_files)
