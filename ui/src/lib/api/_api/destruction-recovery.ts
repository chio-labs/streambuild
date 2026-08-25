import { readApiResponse } from '$lib/api/_api/read-response';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';
import type { DestructionPlan } from '$lib/pipeline-view/types';

export async function requestDestructionRecoveryPlan(
	invocationId: string
): Promise<DestructionPlan> {
	const response: Response = await authenticatedFetch(
		`/api/runs/${encodeURIComponent(invocationId)}/recovery-plan`,
		{ method: 'POST' }
	);
	return readApiResponse<DestructionPlan>(response, 'destruction recovery plan');
}
