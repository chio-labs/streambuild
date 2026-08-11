import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestProjectReload } from '$lib/api/_api/project-actions';

describe('project action API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given a reload request when sent then the project reload endpoint receives a post', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response('{"compile":{"state":"ok"}}'))
		);
		vi.stubGlobal('fetch', fetchMock);

		await requestProjectReload();

		expect(fetchMock).toHaveBeenCalledWith('/api/reload', { method: 'POST' });
	});
});
