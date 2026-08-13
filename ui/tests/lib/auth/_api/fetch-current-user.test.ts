import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchCurrentUser } from '$lib/auth/_api/fetch-current-user';

describe('current user API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given an unauthenticated response when requested then no user is returned', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

		await expect(fetchCurrentUser()).resolves.toBeNull();
	});
});
