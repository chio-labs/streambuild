"""Entry naming deployed managed sources whose settings drifted and the pipelines owning them."""

from __future__ import annotations

from streambuild.adapter.models import CatalogSnapshot
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.executor.direct._helpers.sources import (
    drifted_managed_sources as _drifted_managed_sources,
)
from streambuild.executor.direct.models import DriftedManagedSource


def drifted_managed_sources(
    *, realized_project: RealizedProject, catalog: CatalogSnapshot
) -> tuple[DriftedManagedSource, ...]:
    """Return deployed managed sources whose settings drifted, ordered by source name."""

    return _drifted_managed_sources(realized_project=realized_project, catalog=catalog)
