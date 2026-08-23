import { describe, expect, it } from 'vitest';

import { planFromServer, projectFromServer } from '$lib/api/_helpers/mapping';
import type { Project } from '$lib/domain/types';
import type { Plan } from '$lib/planning/types';

describe('plan mapping', () => {
	it('given a virtual server plan when mapped then mode phases and deployment stay intact', () => {
		const plan: Plan = planFromServer(
			{
				mode: 'virtual',
				database: 'analytics',
				deploymentId: '20260811T120000Z_plan',
				executionOrder: ['virtual'],
				phases: [
					{
						mode: 'virtual',
						effect: 'staged',
						deploymentId: '20260811T120000Z_plan',
						modelNames: ['orders'],
						contextModelNames: ['order_events'],
						relationNames: ['tbl__orders__20260811T120000Z_plan'],
						actions: [
							{
								phase: 'plan',
								action: 'plan_shadow_table',
								logicalName: 'orders',
								physicalName: 'tbl__orders__20260811T120000Z_plan'
							}
						],
						startTime: '2026-08-10 12:00:00.000'
					}
				],
				warnings: [
					{ code: 'bounded_replay', message: 'Replay is bounded.', relatedModel: 'orders' }
				],
				upperBoundary: { mode: 'captured_at_execution', continuesLive: true }
			},
			'clickhouse'
		);

		expect(plan.mode).toBe('virtual');
		expect(plan.deploymentId).toBe('20260811T120000Z_plan');
		expect(plan.executionOrder).toEqual(['virtual']);
		expect(plan.phases[0]?.actions[0]?.logicalName).toBe('orders');
		expect(plan.warnings[0]?.relatedModel).toBe('orders');
		expect(plan.upperBoundary.continuesLive).toBe(true);
	});
});

describe('project mapping', () => {
	it('given unconfigured freshness when mapped then source and model freshness stay unknown', () => {
		const project: Project = projectFromServer(
			{
				project: {},
				sources: [{ name: 'orders' }],
				pipelines: [],
				models: [{ name: 'orders_clean', sql: {}, anchor: 'eligible' }],
				audits: [],
				tests: [],
				macros: []
			},
			{
				capturedAt: '2026-08-23T10:00:00Z',
				sources: { orders: { freshness: null } },
				models: { orders_clean: { freshness: null } }
			}
		);

		expect(project.sources[0]?.live.freshness).toBeNull();
		expect(project.models[0]?.status).toBe('unknown');
	});
});
