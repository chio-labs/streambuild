"""Pipeline models for authored pipeline specifications."""

from dataclasses import dataclass, field

from streambuild.spec.models.steps import ExternalTableSourceStep, KafkaLandingStep, TransformStep
from streambuild.spec.models.types import BoundedReplayFallback, ReplayLineageMode


@dataclass(frozen=True)
class Pipeline:
    """A single authored streaming pipeline."""

    name: str
    source: KafkaLandingStep | ExternalTableSourceStep
    transforms: list[TransformStep] = field(default_factory=list)
    replay_lineage_mode: ReplayLineageMode | str | None = None
    bounded_replay_fallback: BoundedReplayFallback | str | None = None

    def __post_init__(self) -> None:
        if self.replay_lineage_mode is not None:
            object.__setattr__(
                self,
                "replay_lineage_mode",
                ReplayLineageMode(self.replay_lineage_mode),
            )
        if self.bounded_replay_fallback is not None:
            object.__setattr__(
                self,
                "bounded_replay_fallback",
                BoundedReplayFallback(self.bounded_replay_fallback),
            )
