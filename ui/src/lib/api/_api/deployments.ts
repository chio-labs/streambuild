import { readApiResponse } from '$lib/api/_api/read-response';
import type { DeploymentDiff } from '$lib/api/types';
import type { Deployment, DeploymentDetail } from '$lib/domain/types';

export async function requestDeployments(): Promise<Deployment[]> {
	const response: Response = await fetch('/api/deployments');
	const payload: { deployments: Deployment[] } = await readApiResponse<{
		deployments: Deployment[];
	}>(response, 'deployments');
	return payload.deployments;
}

export async function requestDeployment(
	deploymentId: string,
	signal?: AbortSignal
): Promise<DeploymentDetail> {
	const response: Response = await fetch(`/api/deployments/${encodeURIComponent(deploymentId)}`, {
		signal
	});
	return readApiResponse<DeploymentDetail>(response, 'deployment');
}

export async function requestDeploymentDiff(
	deploymentId: string,
	against: string | null
): Promise<DeploymentDiff> {
	const query: string = against === null ? '' : `?against=${encodeURIComponent(against)}`;
	const response: Response = await fetch(
		`/api/deployments/${encodeURIComponent(deploymentId)}/diff${query}`
	);
	return readApiResponse<DeploymentDiff>(response, 'deployment diff');
}
