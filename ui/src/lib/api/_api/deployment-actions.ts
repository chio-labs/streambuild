import { readApiResponse } from '$lib/api/_api/read-response';
import type { CleanupResult, PromoteResult } from '$lib/api/types';

export async function requestDeploymentPromotion(deploymentId: string): Promise<PromoteResult> {
	const response: Response = await fetch(`/api/deployments/${encodeURIComponent(deploymentId)}/promote`, {
		method: 'POST'
	});
	return readApiResponse<PromoteResult>(response, 'deployment promote');
}

export async function requestDeploymentCleanup(retentionDays: number): Promise<CleanupResult> {
	const response: Response = await fetch('/api/deployments/cleanup', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ retentionDays })
	});
	return readApiResponse<CleanupResult>(response, 'deployment cleanup');
}
