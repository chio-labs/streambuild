"""Mutable relation evidence accumulated during destruction planning."""

from streambuild.executor.destruction.types import (
    DestructionOwnership,
    DestructionRelationKind,
)


class OwnedRelation:
    def __init__(
        self,
        *,
        name: str,
        kind: DestructionRelationKind,
        logical_name: str,
        pipeline_name: str | None,
        ownership: DestructionOwnership,
    ) -> None:
        self.name: str = name
        self.kind: DestructionRelationKind = kind
        self.logical_names: set[str] = {logical_name}
        self.pipeline_names: set[str] = set() if pipeline_name is None else {pipeline_name}
        self.ownership: set[DestructionOwnership] = {ownership}

    def merge(
        self,
        *,
        kind: DestructionRelationKind,
        logical_name: str,
        pipeline_name: str | None,
        ownership: DestructionOwnership,
        kind_rank: int,
        current_kind_rank: int,
    ) -> None:
        if kind_rank < current_kind_rank:
            self.kind = kind
        self.logical_names.add(logical_name)
        if pipeline_name is not None:
            self.pipeline_names.add(pipeline_name)
        self.ownership.add(ownership)
