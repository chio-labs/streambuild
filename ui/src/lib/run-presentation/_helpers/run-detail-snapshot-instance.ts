import { createRunDetailSnapshotResource } from '$lib/run-presentation/_resources/run-detail-snapshot.resource';
import type { RunDetailSnapshotResource } from '$lib/run-presentation/types';

let instance: RunDetailSnapshotResource | null = null;

export function getRunDetailSnapshotResource(): RunDetailSnapshotResource {
	if (instance === null) instance = createRunDetailSnapshotResource();
	return instance;
}
