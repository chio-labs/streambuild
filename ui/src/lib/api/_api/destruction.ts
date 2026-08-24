import { readApiResponse } from '$lib/api/_api/read-response';
import type {
	DestructionExecution,
	DestructionOperation,
	DestructionPlan,
	ReviewedDestructionPlan
} from '$lib/pipeline-view/types';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';

export async function requestDestructionPlan(
	operation: DestructionOperation,
	pipelineNames: string[],
	includedDependentPipelineNames: string[]
): Promise<DestructionPlan> {
	const response: Response = await authenticatedFetch('/api/destruction/plans', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ operation, pipelineNames, includedDependentPipelineNames })
	});
	return readApiResponse<DestructionPlan>(response, 'destruction plan');
}

export async function requestDestructionPlanReview(
	planId: string
): Promise<ReviewedDestructionPlan> {
	const response: Response = await authenticatedFetch(
		`/api/destruction/plans/${encodeURIComponent(planId)}/review`,
		{ method: 'POST' }
	);
	return readApiResponse<ReviewedDestructionPlan>(response, 'destruction plan review');
}

export async function requestDestructionExecution(
	planId: string,
	responses: string[]
): Promise<DestructionExecution> {
	const response: Response = await authenticatedFetch(
		`/api/destruction/plans/${encodeURIComponent(planId)}/execute`,
		{
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ responses })
		}
	);
	return readApiResponse<DestructionExecution>(response, 'destruction execution');
}
