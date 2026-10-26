import { STRUCTURED_PLAN_WARNING_CODES } from '$lib/planning/constants';
import type { Plan } from '$lib/planning/types';
import type { PlanSummary } from '$lib/plan-view/types';

type PlanEntryReason = Plan['entries'][number]['reason'];

export function summarizePlan(plan: Plan | null): PlanSummary {
	const planEntries: Plan['entries'] = plan?.entries ?? [];
	const replayRoots: Plan['replayRoots'] = plan?.replayRoots ?? [];
	const sourceRecreations: Plan['sourceRecreations'] = plan?.sourceRecreations ?? [];
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
		sourceDriftCount: planEntries.filter((entry) => entry.reason === 'source_drift').length,
		downstreamCount: planEntries.filter((entry) => entry.reason === 'downstream_of_selected').length,
		missingUpstreamCount: planEntries.filter((entry) => entry.reason === 'missing_upstream').length,
		riskyOwnership: planEntries.flatMap((entry) =>
			entry.ownership.filter((item) => item.ownership !== 'direct' && item.ownership !== 'absent')
		),
		sourceRecreations,
		plannerWarnings: (plan?.warnings ?? []).filter(
			(warning) =>
				sourceRecreations.length === 0 || !STRUCTURED_PLAN_WARNING_CODES.has(warning.code)
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

const PLAN_ENTRY_BADGE: Readonly<Partial<Record<PlanEntryReason, string>>> = {
	downstream_of_selected: 'downstream',
	source_drift: 'source drift'
};

/** Short badge for why a model is in the plan; source drift reads as words, not an identifier. */
export function planReasonBadge(reason: PlanEntryReason): string {
	return PLAN_ENTRY_BADGE[reason] ?? reason;
}
