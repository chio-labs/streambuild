import { readApiResponse } from '$lib/api/_api/read-response';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';
import type { DestructionPlan } from '$lib/pipeline-view/types';

export async function requestStoredDestructionPlan(
	planId: string,
	signal?: AbortSignal
): Promise<DestructionPlan> {
	const response: Response = await authenticatedFetch(
		`/api/destruction/plans/${encodeURIComponent(planId)}`,
		{ signal }
	);
	return readApiResponse<DestructionPlan>(response, 'stored destruction plan');
}
