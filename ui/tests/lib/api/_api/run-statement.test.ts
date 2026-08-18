import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestRunStatement } from '$lib/api/_api/run-statement';

describe('run statement API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given a run and sequence when the statement endpoint is requested then transport preserves its contract', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() => Promise.resolve(new Response('{}')));
		vi.stubGlobal('fetch', fetchMock);

		await requestRunStatement('run/id', 7);

		expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/runs/run%2Fid/statements/7');
	});
});
