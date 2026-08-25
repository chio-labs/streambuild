import { requestStoredDestructionPlan } from '$lib/api/_api/destruction-plan';
import type { DestructionPlan } from '$lib/pipeline-view/types';

export async function fetchDestructionPlan(
	planId: string,
	signal?: AbortSignal
): Promise<DestructionPlan> {
	return requestStoredDestructionPlan(planId, signal);
}
