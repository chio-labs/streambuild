import { afterEach, describe, expect, it, vi } from 'vitest';

const controller = vi.hoisted(() => ({
	auth: { csrfToken: null, user: { authenticationSource: 'trusted_proxy' } },
	markUnauthenticated: vi.fn()
}));

vi.mock('$lib/auth/_helpers/auth-instance.svelte', () => ({ getAuthInstance: () => controller }));

import { requestWithAuthentication } from '$lib/auth/_api/authenticated-fetch';

describe('authenticated fetch', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given a proxy principal when mutating then request proof is attached', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn().mockResolvedValue(new Response('{}'));
		vi.stubGlobal('fetch', fetchMock);

		await requestWithAuthentication('/api/example', { method: 'POST' });

		const requestInit: RequestInit = fetchMock.mock.calls[0][1];
		expect(new Headers(requestInit.headers).get('X-StreamBuild-CSRF')).toBe('trusted-proxy');
	});
});
