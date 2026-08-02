"""Publish canonical direct ownership classification."""

from streambuild.compiler.planner._helpers.direct_ownership import classify_relation_ownership
from streambuild.compiler.planner.models import (
    DirectWarehouseSnapshot,
    TargetOwnershipClassification,
)


def classify_direct_ownership(
    *, snapshot: DirectWarehouseSnapshot, relation_names: tuple[str, ...]
) -> tuple[TargetOwnershipClassification, ...]:
    """Classify requested relations from the current catalog and ownership evidence."""

    return classify_relation_ownership(snapshot=snapshot, relation_names=relation_names)
