import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestBootstrapPayload } from '$lib/api/_api/bootstrap';
import type { BootstrapPayload } from '$lib/api/types';

const BOOTSTRAP_PAYLOAD = {
	auth: {
		config: { mode: 'disabled', loginRequired: false, proxyLogoutUrl: null },
		session: {
			mode: 'disabled',
			user: {
				id: '00000000-0000-4000-8000-000000000001',
				username: 'local',
				displayName: 'Local user',
				email: null,
				authenticationSource: 'local'
			},
			roles: ['admin'],
			csrfToken: null
		},
		capabilities: {
			systemAdmin: true,
			project: 'example',
			target: null,
			permissions: [],
			pipelinePermissions: {},
			staleRoles: []
		}
	},
	status: {},
	definitions: {},
	state: null
};

describe('bootstrap API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given an authenticated bootstrap response when requested then the complete payload is validated', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi
			.fn()
			.mockResolvedValue(new Response(JSON.stringify(BOOTSTRAP_PAYLOAD)));
		vi.stubGlobal('fetch', fetchMock);

		const payload: BootstrapPayload | null = await requestBootstrapPayload();

		expect(fetchMock).toHaveBeenCalledOnce();
		expect(fetchMock).toHaveBeenCalledWith('/api/bootstrap');
		expect(payload).toEqual(BOOTSTRAP_PAYLOAD);
	});

	it('given an expired session when bootstrap returns unauthorized then login fallback is requested', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 401 })));

		const payload: BootstrapPayload | null = await requestBootstrapPayload();

		expect(payload).toBeNull();
	});
});
