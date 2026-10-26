"""Describe one drifted managed source recreation for plan surfaces."""

from __future__ import annotations

from streambuild.cli.plan._helpers.direct_rendering import (
    render_source_recreation_notice as _render_source_recreation_notice,
)
from streambuild.executor.population.models import PopulationSourceRecreation


def render_source_recreation_notice(recreation: PopulationSourceRecreation) -> str:
    """Return the single plan line describing one managed source recreation."""

    return _render_source_recreation_notice(recreation)
