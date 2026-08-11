import { OWNERSHIP_LABEL } from '$lib/domain/constants';
import { formatAgo } from '$lib/formatting/main/format-ago';
import { formatClock } from '$lib/formatting/main/format-clock';
import { formatCompact } from '$lib/formatting/main/format-compact';
import { formatDuration } from '$lib/formatting/main/format-duration';
import { selectorToken } from '$lib/planning/main/selector-token';
import { rootSourcesFor } from '$lib/domain/main/planning/root-sources-for';
import { parsePlanCommand } from '$lib/plan-view/_helpers/plan-command';
import {
	planLocationRequestKey,
	readPlanLocation,
	replayStartToken,
	shouldClearReplayStart,
	writePlanDeployment,
	writePlanSelection
} from '$lib/plan-view/_helpers/plan-location';
import { planBoundaryColumns } from '$lib/plan-view/_helpers/plan-presentation';
import type { PlanViewFacade } from '$lib/plan-view/types';

export function createPlanView(): PlanViewFacade {
	return {
		readLocation: readPlanLocation,
		locationRequestKey: planLocationRequestKey,
		shouldClearReplayStart,
		selectionUrl: writePlanSelection,
		deploymentUrl: writePlanDeployment,
		replayStartToken,
		parseCommand: parsePlanCommand,
		boundaryColumns: planBoundaryColumns,
		rootSources: rootSourcesFor,
		selectorToken,
		formatAgo,
		formatClock,
		formatCompact,
		formatDuration,
		sqlChangeLabel: {
			first_baseline: 'first build',
			query_changed: 'SQL changed',
			no_query_change: 'no SQL change',
			baseline_unavailable: 'baseline unavailable'
		},
		sqlChangeColour: {
			first_baseline: 'var(--primary)',
			query_changed: 'var(--sb-warning)',
			no_query_change: 'var(--sb-text-faint)',
			baseline_unavailable: 'var(--sb-warning)'
		},
		ownershipLabel: OWNERSHIP_LABEL
	};
}
