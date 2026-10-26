export const PLAN_REASON_LABEL: Record<string, string> = {
	selected: 'selected',
	downstream_of_selected: 'downstream of selection',
	all_models: 'all models'
};

/** Planner warning codes the plan view presents as structured changes instead of warnings. */
export const STRUCTURED_PLAN_WARNING_CODES: ReadonlySet<string> = new Set([
	'managed_source_recreated'
]);
