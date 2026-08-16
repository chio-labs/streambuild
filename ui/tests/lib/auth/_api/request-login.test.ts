import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestLogin } from '$lib/auth/_api/request-login';
import type { AuthPayload } from '$lib/auth/types';

describe('login API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given credentials when signing in then the decoded principal is returned', async () => {
		const payload: AuthPayload = { mode: 'password', user: { id: 'd0b46a1e-7553-47bd-9188-fcf59fbed050', username: 'alice', displayName: null, email: null, authenticationSource: 'password' }, roles: ['viewer'], csrfToken: 'proof' };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(payload))));

		await expect(requestLogin('alice', 'password')).resolves.toMatchObject({ roles: ['viewer'] });
	});
});
