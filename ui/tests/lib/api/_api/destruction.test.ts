import { afterEach, describe, expect, it, vi } from 'vitest';

import {
	requestDestructionExecution,
	requestDestructionPlan,
	requestDestructionPlanReview
} from '$lib/api/_api/destruction';

const plan = {
	planId: 'plan/one',
	planFingerprint: 'sha256:frozen',
	operation: 'destroy_pipelines',
	target: 'production',
	database: 'analytics',
	selectedPipelines: ['orders'],
	includedDependentPipelines: [],
	affectedPipelines: ['orders'],
	requiredDependentPipelines: [],
	blocked: false,
	models: ['fact_orders'],
	resources: [],
	managedSourcesIncluded: false,
	retainedReplayDataIncluded: false,
	estimatedBytes: 0,
	challengeValues: ['orders'],
	expiresAt: '2026-08-24T12:15:00Z'
};

describe('destruction API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given destruction inputs when requests are made then exact endpoint contracts omit confirmation bypass fields', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi
			.fn()
			.mockResolvedValueOnce(new Response(JSON.stringify(plan)))
			.mockResolvedValueOnce(
				new Response(JSON.stringify({ ...plan, reviewedAt: '2026-08-24T12:01:00Z' }))
			)
			.mockResolvedValueOnce(
				new Response(JSON.stringify({ invocationId: 'destroy-1', status: 'running' }))
			);
		vi.stubGlobal('fetch', fetchMock);

		await requestDestructionPlan('destroy_pipelines', ['orders'], ['customers']);
		await requestDestructionPlanReview('plan/one');
		await requestDestructionExecution('plan/one', ['orders', 'customers']);

		expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/destruction/plans', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({
				operation: 'destroy_pipelines',
				pipelineNames: ['orders'],
				includedDependentPipelineNames: ['customers']
			})
		});
		expect(fetchMock).toHaveBeenNthCalledWith(
			2,
			'/api/destruction/plans/plan%2Fone/review',
			{ method: 'POST' }
		);
		expect(fetchMock).toHaveBeenNthCalledWith(
			3,
			'/api/destruction/plans/plan%2Fone/execute',
			{
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ responses: ['orders', 'customers'] })
			}
		);

		const requestBodies: Record<string, unknown>[] = [0, 2].map((callIndex) =>
			JSON.parse(String(fetchMock.mock.calls[callIndex][1]?.body))
		);
		expect(Object.keys(requestBodies[0])).toEqual([
			'operation',
			'pipelineNames',
			'includedDependentPipelineNames'
		]);
		expect(Object.keys(requestBodies[1])).toEqual(['responses']);
		for (const body of requestBodies) {
			expect(body).not.toHaveProperty('confirmation');
			expect(body).not.toHaveProperty('confirmations');
			expect(body).not.toHaveProperty('confirmed');
			expect(body).not.toHaveProperty('force');
			expect(body).not.toHaveProperty('bypass');
		}
	});

	it('given a target reset when a plan is requested then the pipeline selection is empty', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response(JSON.stringify({ ...plan, operation: 'reset_target' })))
		);
		vi.stubGlobal('fetch', fetchMock);

		await requestDestructionPlan('reset_target', [], []);

		expect(fetchMock).toHaveBeenCalledWith('/api/destruction/plans', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({
				operation: 'reset_target',
				pipelineNames: [],
				includedDependentPipelineNames: []
			})
		});
	});
});
