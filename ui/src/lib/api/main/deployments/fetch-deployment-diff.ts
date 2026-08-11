import { requestDeploymentDiff } from '$lib/api/_api/deployments';
import type { DeploymentDiff } from '$lib/api/types';

export async function fetchDeploymentDiff(
	deploymentId: string,
	against: string | null = null
): Promise<DeploymentDiff> {
	return requestDeploymentDiff(deploymentId, against);
}
