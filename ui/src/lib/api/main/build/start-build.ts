import { requestBuildStart } from '$lib/api/_api/build';
import type { BuildStartResult } from '$lib/api/types';

export async function startBuild(
	selectors: string[],
	startTime: string | null,
	confirmations: string[] = [],
	deploymentId: string | null = null,
	changed: boolean = false,
	includeMissingUpstream: boolean = false
): Promise<BuildStartResult> {
	return requestBuildStart(
		selectors,
		startTime,
		confirmations,
		deploymentId,
		changed,
		includeMissingUpstream
	);
}
