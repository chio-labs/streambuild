import { requestBuildStart } from '$lib/api/_api/build';
import type { BuildStartResult } from '$lib/api/types';

export async function startBuild(
	selectors: string[],
	startTime: string | null,
	confirmations: string[] = []
): Promise<BuildStartResult> {
	return requestBuildStart(selectors, startTime, confirmations);
}
