import { requestBuildFeed } from '$lib/api/_api/build';
import type { BuildFeed } from '$lib/api/types';

export async function fetchBuildFeed(after: number): Promise<BuildFeed> {
	return requestBuildFeed(after);
}
