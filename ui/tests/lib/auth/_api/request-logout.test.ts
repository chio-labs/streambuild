import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestLogout } from '$lib/auth/_api/request-logout';

describe('logout API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given a CSRF token when signing out then the request carries it', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn().mockResolvedValue(new Response('{"status":"ok"}'));
		vi.stubGlobal('fetch', fetchMock);

		await requestLogout('proof');

		expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({ headers: { 'X-StreamBuild-CSRF': 'proof' } }));
	});
});
