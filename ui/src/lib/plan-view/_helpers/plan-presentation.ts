import type { Plan } from '$lib/planning/types';
import type { PlanSummary } from '$lib/plan-view/types';

export function summarizePlan(plan: Plan | null): PlanSummary {
	const planEntries: Plan['entries'] = plan?.entries ?? [];
	const replayRoots: Plan['replayRoots'] = plan?.replayRoots ?? [];
	return {
		planEntries,
		plannedModelNames: Array.from(
			new Set((plan?.phases ?? []).flatMap((phase) => phase.modelNames))
		),
		plannedRelationNames: Array.from(
			new Set((plan?.phases ?? []).flatMap((phase) => phase.relationNames))
		),
		hasDirectPhase: (plan?.phases ?? []).some(
			(phase) => phase.mode === 'direct' && phase.modelNames.length > 0
		),
		rowsToReplay:
			replayRoots.length === 0 || replayRoots.some((root) => root.rowsToReplay === null)
				? null
				: replayRoots.reduce((total, root) => total + (root.rowsToReplay ?? 0), 0),
		selectedCount: planEntries.filter((entry) => entry.reason === 'selected').length,
		changedCount: planEntries.filter((entry) => entry.reason === 'changed').length,
		downstreamCount: planEntries.filter((entry) => entry.reason === 'downstream_of_selected').length,
		missingUpstreamCount: planEntries.filter((entry) => entry.reason === 'missing_upstream').length,
		riskyOwnership: planEntries.flatMap((entry) =>
			entry.ownership.filter((item) => item.ownership !== 'direct' && item.ownership !== 'absent')
		)
	};
}

export function planBoundaryColumns(root: Plan['replayRoots'][number]): string | null {
	const columns: Plan['replayRoots'][number]['replayColumns'] = root.replayColumns;
	if (root.boundaryMode === 'offsets') {
		const pair: string = [columns.partition, columns.offset].filter(Boolean).join(' / ');
		return pair || null;
	}
	if (root.boundaryMode === 'timestamp' || root.boundaryMode === 'cursor') {
		return columns.timestamp ?? null;
	}
	return columns.landed_at ?? null;
}
