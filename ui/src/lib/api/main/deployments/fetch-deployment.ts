import { requestDeployment } from '$lib/api/_api/deployments';
import type { DeploymentDetail } from '$lib/domain/types';

export async function fetchDeployment(
	deploymentId: string,
	signal?: AbortSignal
): Promise<DeploymentDetail> {
	return requestDeployment(deploymentId, signal);
}
