import { requestDestructionExecution } from '$lib/api/_api/destruction';
import type { DestructionExecution } from '$lib/pipeline-view/types';

export async function executeDestructionPlan(
	planId: string,
	responses: string[]
): Promise<DestructionExecution> {
	return requestDestructionExecution(planId, responses);
}
