import { describe, expect, it } from 'vitest';

import { buildPlanCommand } from '$lib/plan-view/_helpers/build-command';
import type { BuildCommandParts } from '$lib/plan-view/types';
import type { Plan, Selector } from '$lib/planning/types';

function directPlan(): Plan {
	return { command: 'stb build', deploymentId: null, mode: 'direct' } as unknown as Plan;
}

function virtualPlan(deploymentId: string): Plan {
	return { command: 'stb build', deploymentId, mode: 'virtual' } as unknown as Plan;
}

function parts(overrides: Partial<BuildCommandParts>): BuildCommandParts {
	return {
		selectors: [],
		changed: false,
		includeMissingUpstream: false,
		replayWindow: { mode: 'full' },
		acceptedConfirmations: [],
		plan: null,
		planLoading: false,
		...overrides
	};
}

describe('build plan command', () => {
	it('given no selection when built then it names an all-models direct build', () => {
		expect(buildPlanCommand(parts({}))).toBe('stb build');
	});

	it('given model and pipeline selectors when built then each becomes a --select token', () => {
		const selectors: Selector[] = [
			{ kind: 'model', name: 'orders' },
			{ kind: 'pipeline', name: 'pl__payments' }
		];

		expect(buildPlanCommand(parts({ selectors }))).toBe(
			'stb build --select orders pipeline:pl__payments'
		);
	});

	it('given a replay start time when built then --start-time follows the selection', () => {
		const built: string = buildPlanCommand(
			parts({
				selectors: [{ kind: 'model', name: 'orders' }],
				replayWindow: { mode: 'from', startTime: '2026-08-10T12:00:00.000Z' }
			})
		);

		expect(built).toBe('stb build --select orders --start-time 2026-08-10T12:00:00Z');
	});

	it('given a resolved virtual plan when built then its deployment id is appended', () => {
		const built: string = buildPlanCommand(
			parts({
				selectors: [{ kind: 'model', name: 'orders' }],
				plan: virtualPlan('20260811T120000Z_plan')
			})
		);

		expect(built).toBe('stb build --select orders --deployment-id 20260811T120000Z_plan');
	});

	it('given a re-plan still in flight when built then the stale deployment id is withheld', () => {
		const built: string = buildPlanCommand(
			parts({
				selectors: [{ kind: 'model', name: 'orders' }],
				plan: virtualPlan('20260811T120000Z_plan'),
				planLoading: true
			})
		);

		expect(built).toBe('stb build --select orders');
	});

	it('given a resolved direct plan when built then no deployment id is emitted', () => {
		const built: string = buildPlanCommand(
			parts({ selectors: [{ kind: 'model', name: 'orders' }], plan: directPlan() })
		);

		expect(built).toBe('stb build --select orders');
	});

	it('given accepted confirmations when built then each trails as a --confirm flag', () => {
		const built: string = buildPlanCommand(
			parts({
				selectors: [{ kind: 'model', name: 'orders' }],
				acceptedConfirmations: ['drop-orders', 'drop-lineitems']
			})
		);

		expect(built).toBe(
			'stb build --select orders --confirm drop-orders --confirm drop-lineitems'
		);
	});

	it('given changed models with missing upstream enabled when built then both native flags are emitted', () => {
		expect(
			buildPlanCommand(
				parts({
					changed: true,
					includeMissingUpstream: true
				})
			)
		).toBe('stb build --changed --include-missing-upstream');
	});

	it('given changed mode and stale selectors when built then changed mode wins', () => {
		expect(
			buildPlanCommand(
				parts({
					selectors: [{ kind: 'model', name: 'orders' }],
					changed: true
				})
			)
		).toBe('stb build --changed');
	});
});
