import { requestDestructionPlan } from '$lib/api/_api/destruction';
import type { DestructionOperation, DestructionPlan } from '$lib/pipeline-view/types';

export async function createDestructionPlan(
	operation: DestructionOperation,
	pipelineNames: string[],
	includedDependentPipelineNames: string[] = []
): Promise<DestructionPlan> {
	return requestDestructionPlan(operation, pipelineNames, includedDependentPipelineNames);
}
