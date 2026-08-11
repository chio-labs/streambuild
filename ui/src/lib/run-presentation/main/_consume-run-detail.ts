import { getRunDetailSnapshotResource } from '$lib/run-presentation/_helpers/run-detail-snapshot-instance';
import type { RunDetailSnapshot } from '$lib/run-presentation/types';

export function consumeRunDetail(invocationId: string): Promise<RunDetailSnapshot> {
	return getRunDetailSnapshotResource().consume(invocationId);
}
