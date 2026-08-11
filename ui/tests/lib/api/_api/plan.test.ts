import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestPlan } from '$lib/api/_api/plan';

describe('plan API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given selectors and a start time when a plan is requested then repeated selectors are encoded', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response('{"steps":[]}'))
		);
		vi.stubGlobal('fetch', fetchMock);

		await requestPlan(['model:orders', 'source:events'], '2026-08-10T12:00:00Z');

		expect(fetchMock).toHaveBeenCalledWith(
			'/api/plan?select=model%3Aorders&select=source%3Aevents&start=2026-08-10T12%3A00%3A00Z'
		);
	});
});
