import { requestDeploymentPromotion } from '$lib/api/_api/deployment-actions';
import type { PromoteResult } from '$lib/api/types';

export async function promoteDeployment(deploymentId: string): Promise<PromoteResult> {
	return requestDeploymentPromotion(deploymentId);
}
