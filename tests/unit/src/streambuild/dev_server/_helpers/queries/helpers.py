from streambuild.adapter.models import (
    AdapterReplayOffsetProgressRequest,
    AdapterReplayOffsetRange,
)


def replay_progress_request(
    *ranges: AdapterReplayOffsetRange,
) -> AdapterReplayOffsetProgressRequest:
    return AdapterReplayOffsetProgressRequest(
        database="analytics",
        relation="tbl__orders",
        partition_column="_replay_partition",
        offset_column="_replay_offset",
        ranges=ranges,
    )
