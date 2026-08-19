import type { PlanStatus, PlanStatusInput } from '$lib/plan-view/types';

/**
 * Reduce the plan request lifecycle to one status for the whole server-computed
 * region. Every plan section reads this, so a failed or pending request can
 * never leave an earlier scope rendered on screen.
 */
export function planStatusFor(input: PlanStatusInput): PlanStatus {
	if (input.planError !== null) return 'error';
	if (input.planLoading) return 'loading';
	return input.plan !== null ? 'ready' : 'empty';
}
