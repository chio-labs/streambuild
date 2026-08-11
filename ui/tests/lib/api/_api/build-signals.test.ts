import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestBuildCancellation, requestBuildKill } from '$lib/api/_api/build-signals';

describe('build signal API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given invocation ids when cancellation and kill are requested then each signal is posted', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response('{"accepted":true}'))
		);
		vi.stubGlobal('fetch', fetchMock);

		await requestBuildCancellation('cancel/id');
		await requestBuildKill('kill/id');

		expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/build/cancel', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ invocationId: 'cancel/id' })
		});
		expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/build/kill', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ invocationId: 'kill/id' })
		});
	});
});
