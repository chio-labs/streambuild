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

	it('given warehouse health when mapped then zero and unknown measurements remain distinct', () => {
		const project: Project = projectFromServer(
			{
				project: {},
				sources: [],
				pipelines: [],
				models: [],
				audits: [],
				tests: [],
				macros: []
			},
			{
				capturedAt: '2026-08-23T10:00:00Z',
				warehouseHealth: {
					availability: 'partial',
					status: 'critical',
					adapter: 'clickhouse',
					database: 'analytics',
					version: '25.8.1.1',
					uptimeSeconds: 86400,
					measuredAt: '2026-08-23T10:00:00Z',
					collectionDurationMs: 4,
					stale: false,
					warnings: ['Main-path inode metrics are unavailable.'],
					disks: [
						{
							name: 'default',
							path: '/data/',
							type: 'Local',
							totalBytes: 100,
							freeBytes: 0,
							unreservedBytes: 0,
							keepFreeBytes: 0,
							status: 'critical'
						}
					],
					inodes: { total: null, free: null, status: 'unknown' },
					memory: {
						residentBytes: 50,
						hostTotalBytes: 1000,
						cgroupUsedBytes: null,
						cgroupLimitBytes: null,
						basis: 'server_rss_host',
						pressureFraction: null
					},
					activity: { activeQueries: 0, activeMerges: 0, incompleteMutations: 0 },
					tables: []
				}
			}
		);

		expect(project.warehouseHealth?.disks[0]?.freeBytes).toBe(0);
		expect(project.warehouseHealth?.inodes.free).toBeNull();
		expect(project.warehouseHealth?.memory?.basis).toBe('server_rss_host');
		expect(project.warehouseHealth?.database).toBe('analytics');
		expect(project.warehouseHealth?.activity?.activeQueries).toBe(0);
	});

	it('given no warehouse health when mapped then diagnostics remain unavailable', () => {
		const project: Project = projectFromServer(
			{
				project: {},
				sources: [],
				pipelines: [],
				models: [],
				audits: [],
				tests: [],
				macros: []
			},
			{ capturedAt: '2026-08-23T10:00:00Z' }
		);

		expect(project.warehouseHealth).toBeNull();
	});
});
