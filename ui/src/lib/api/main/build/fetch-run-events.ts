import { requestRunEvents } from '$lib/api/_api/build';
import type { RunEventFeed } from '$lib/api/types';

export async function fetchRunEvents(
	invocationId: string,
	after: number = 0
): Promise<RunEventFeed> {
	return requestRunEvents(invocationId, after);
}
