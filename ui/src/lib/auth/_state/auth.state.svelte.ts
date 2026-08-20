import { fetchAuthConfig } from '../_api/fetch-auth-config';
import { fetchCapabilities } from '../_api/fetch-capabilities';
import { fetchCurrentUser } from '../_api/fetch-current-user';
import { requestLogin } from '../_api/request-login';
import { requestLogout } from '../_api/request-logout';
import type { AuthController, AuthPayload, AuthState } from '../types';

export function createAuthState(): AuthController {
	const auth: AuthState = $state({
		phase: 'loading',
		config: null,
		user: null,
		roles: [],
		csrfToken: null,
		capabilities: null,
		error: null
	});

	async function initialize(): Promise<void> {
		auth.phase = 'loading';
		auth.error = null;
		try {
			auth.config = await fetchAuthConfig();
			const payload: AuthPayload | null = await fetchCurrentUser();
			if (payload === null) {
				auth.phase = auth.config.loginRequired ? 'unauthenticated' : 'error';
				auth.error = auth.config.loginRequired ? null : 'The authenticating proxy did not provide an identity.';
				return;
			}
			apply(payload);
			await refreshCapabilities();
		} catch (error) {
			auth.phase = 'error';
			auth.error = error instanceof Error ? error.message : String(error);
		}
	}

	async function login(username: string, password: string): Promise<void> {
		apply(await requestLogin(username, password));
		await refreshCapabilities();
	}

	function initializeFromBootstrap(
		config: AuthState['config'],
		payload: AuthPayload,
		capabilities: AuthState['capabilities']
	): void {
		auth.config = config;
		apply(payload);
		auth.capabilities = capabilities;
	}

	async function refreshCapabilities(): Promise<void> {
		try {
			auth.capabilities = await fetchCapabilities();
		} catch {
			auth.capabilities = null;
		}
	}

	async function logout(): Promise<void> {
		await requestLogout(auth.csrfToken);
		markUnauthenticated();
	}

	function markUnauthenticated(): void {
		auth.user = null;
		auth.roles = [];
		auth.csrfToken = null;
		auth.capabilities = null;
		auth.phase = 'unauthenticated';
	}

	function apply(payload: AuthPayload): void {
		auth.user = payload.user;
		auth.roles = payload.roles;
		auth.csrfToken = payload.csrfToken;
		auth.phase = 'authenticated';
		auth.error = null;
	}

	return { auth, initialize, initializeFromBootstrap, login, logout, markUnauthenticated };
}
