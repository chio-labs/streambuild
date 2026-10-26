import { describe, expect, it } from 'vitest';

import { summarizePlan } from '$lib/plan-view/_helpers/plan-presentation';
import type { PlanSummary } from '$lib/plan-view/types';
import type { Plan } from '$lib/planning/types';

const RECREATION: Plan['sourceRecreations'][number] = {
	sourceName: 'orders',
	relationName: 'kafka__orders',
	landingViewName: 'mv__orders',
	landingRelationName: 'raw__orders',
	stagedRelationName: '_streambuild_next__kafka__orders',
	consumerGroup: 'streambuild_orders_analytics',
	driftedSettings: ['kafka_max_block_size'],
	message: 'kafka__orders and mv__orders are recreated with the declared settings.'
};
const RECREATION_WARNING: Plan['warnings'][number] = {
	code: 'managed_source_recreated',
	message: RECREATION.message,
	relatedModel: null
};
const REPLAY_WARNING: Plan['warnings'][number] = {
	code: 'bounded_replay',
	message: 'Replay is bounded.',
	relatedModel: 'orders_clean'
};

function planWith(
	sourceRecreations: Plan['sourceRecreations'],
	warnings: Plan['warnings']
): Plan {
	return {
		mode: 'direct',
		deploymentId: null,
		entries: [],
		phases: [],
		replayRoots: [],
		sourceRecreations,
		warnings
	} as unknown as Plan;
}

describe('plan source recreations', () => {
	it('given a recreated source when summarized then it is a change not a planner warning', () => {
		const summary: PlanSummary = summarizePlan(planWith([RECREATION], [RECREATION_WARNING, REPLAY_WARNING]));

		expect(summary.sourceRecreations).toEqual([RECREATION]);
		expect(summary.plannerWarnings).toEqual([REPLAY_WARNING]);
	});

	it('given only the recreation warning from an older server when summarized then the warning stays', () => {
		const summary: PlanSummary = summarizePlan(planWith([], [RECREATION_WARNING]));

		expect(summary.sourceRecreations).toEqual([]);
		expect(summary.plannerWarnings).toEqual([RECREATION_WARNING]);
	});

	it('given no plan when summarized then nothing is recreated or warned', () => {
		const summary: PlanSummary = summarizePlan(null);

		expect(summary.sourceRecreations).toEqual([]);
		expect(summary.plannerWarnings).toEqual([]);
	});
});
