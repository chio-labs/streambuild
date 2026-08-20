import { beforeEach, describe, expect, it, vi } from 'vitest';

const requests = vi.hoisted(() => ({
	fetchAuthConfig: vi.fn(),
	fetchCurrentUser: vi.fn(),
	requestLogin: vi.fn(),
	requestLogout: vi.fn()
}));

vi.mock('$lib/auth/_api/fetch-auth-config', () => ({ fetchAuthConfig: requests.fetchAuthConfig }));
vi.mock('$lib/auth/_api/fetch-current-user', () => ({ fetchCurrentUser: requests.fetchCurrentUser }));
vi.mock('$lib/auth/_api/request-login', () => ({ requestLogin: requests.requestLogin }));
vi.mock('$lib/auth/_api/request-logout', () => ({ requestLogout: requests.requestLogout }));

import { createAuthState } from '$lib/auth/_state/auth.state.svelte';
import type { AuthController } from '$lib/auth/types';

describe('auth state', () => {
	beforeEach(() => vi.clearAllMocks());

	it('given password auth without a session when initialized then login is required', async () => {
		requests.fetchAuthConfig.mockResolvedValue({ mode: 'password', loginRequired: true, proxyLogoutUrl: null });
		requests.fetchCurrentUser.mockResolvedValue(null);
		const controller: AuthController = createAuthState();

		await controller.initialize();

		expect(controller.auth.phase).toBe('unauthenticated');
	});

	it('given bootstrap authentication when initialized then no legacy authentication requests run', () => {
		const controller: AuthController = createAuthState();

		controller.initializeFromBootstrap(
			{ mode: 'disabled', loginRequired: false, proxyLogoutUrl: null },
			{
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
			null
		);

		expect(controller.auth.phase).toBe('authenticated');
		expect(controller.auth.user?.username).toBe('local');
		expect(requests.fetchAuthConfig).not.toHaveBeenCalled();
		expect(requests.fetchCurrentUser).not.toHaveBeenCalled();
	});
});
