import { requestDeploymentCleanup } from '$lib/api/_api/deployment-actions';
import type { CleanupResult } from '$lib/api/types';

export async function cleanupDeployments(retentionDays: number): Promise<CleanupResult> {
	return requestDeploymentCleanup(retentionDays);
}
