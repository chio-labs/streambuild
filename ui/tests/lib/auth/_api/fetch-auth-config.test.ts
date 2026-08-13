import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchAuthConfig } from '$lib/auth/_api/fetch-auth-config';

describe('auth config API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given valid config when requested then the decoded config is returned', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ mode: 'password', loginRequired: true, proxyLogoutUrl: null }))));

		await expect(fetchAuthConfig()).resolves.toMatchObject({ mode: 'password', loginRequired: true });
	});
});
