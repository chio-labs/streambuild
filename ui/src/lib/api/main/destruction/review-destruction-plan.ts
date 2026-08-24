import { requestDestructionPlanReview } from '$lib/api/_api/destruction';
import type { ReviewedDestructionPlan } from '$lib/pipeline-view/types';

export async function reviewDestructionPlan(planId: string): Promise<ReviewedDestructionPlan> {
	return requestDestructionPlanReview(planId);
}
