import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestRuns } from '$lib/api/_api/runs';
import type { RunRecord } from '$lib/api/types';

describe('runs API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given a runs request when the server responds then the run list is returned', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() => Promise.resolve(new Response('[]')));
		vi.stubGlobal('fetch', fetchMock);

		const runs: RunRecord[] = await requestRuns();

		expect(runs).toEqual([]);
		expect(fetchMock).toHaveBeenCalledWith('/api/runs');
	});
});
