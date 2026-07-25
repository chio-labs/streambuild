"""Project-level authored config models."""

from dataclasses import dataclass

from streambuild.spec.models.types import BoundedReplayFallback, ReplayLineageMode


@dataclass(frozen=True)
class ProjectClickHouseConfig:
    """Optional project-level ClickHouse connection defaults."""

    host: str
    port: int
    username: str
    password: str


@dataclass(frozen=True)
class Project:
    """Project-level authored Streambuild config."""

    replay_lineage_mode: ReplayLineageMode | str = ReplayLineageMode.OFFSETS
    bounded_replay_fallback: BoundedReplayFallback | str = BoundedReplayFallback.FULL_REFRESH
    default_database: str | None = None
    clickhouse: ProjectClickHouseConfig | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_lineage_mode", ReplayLineageMode(self.replay_lineage_mode))
        object.__setattr__(
            self,
            "bounded_replay_fallback",
            BoundedReplayFallback(self.bounded_replay_fallback),
        )
