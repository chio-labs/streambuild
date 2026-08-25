import { requestDestructionRecoveryPlan } from '$lib/api/_api/destruction-recovery';
import type { DestructionPlan } from '$lib/pipeline-view/types';

export async function createDestructionRecoveryPlan(
	invocationId: string
): Promise<DestructionPlan> {
	return requestDestructionRecoveryPlan(invocationId);
}
