"""Entry naming the pipelines whose rebuild recreates a drifted managed source."""

from __future__ import annotations

from streambuild.adapter.models import CatalogSnapshot
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.executor.direct._helpers.sources import (
    drifted_managed_source_owners as _drifted_managed_source_owners,
)


def drifted_managed_source_owners(
    *, realized_project: RealizedProject, catalog: CatalogSnapshot
) -> tuple[str, ...]:
    """Return the owning pipelines of deployed managed sources whose settings drifted."""

    return _drifted_managed_source_owners(realized_project=realized_project, catalog=catalog)
