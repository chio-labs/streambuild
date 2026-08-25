import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestPlan } from '$lib/api/_api/plan';

describe('plan API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given selectors and a start time when a plan is requested then repeated selectors are encoded', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response('{"steps":[]}'))
		);
		vi.stubGlobal('fetch', fetchMock);

		await requestPlan({
			selectors: ['model:orders', 'source:events'],
			startTime: '2026-08-10T12:00:00Z',
			deploymentId: '20260811T120000Z_plan'
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/api/plan?select=model%3Aorders&select=source%3Aevents&start=2026-08-10T12%3A00%3A00Z&deployment=20260811T120000Z_plan',
			{ signal: undefined }
		);
	});

	it('given changed mode with missing upstream when requested then snake-case booleans are sent', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response('{"steps":[]}'))
		);
		vi.stubGlobal('fetch', fetchMock);

		await requestPlan({
			selectors: [],
			changed: true,
			includeMissingUpstream: true,
			startTime: null
		});

		expect(fetchMock).toHaveBeenCalledWith(
			'/api/plan?changed=true&include_missing_upstream=true',
			{ signal: undefined }
		);
	});
});
