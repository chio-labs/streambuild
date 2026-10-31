import { getAuthInstance } from '../_helpers/auth-instance.svelte';
import type { AuthController } from '../types';

export function requestWithAuthentication(
	input: RequestInfo | URL,
	init: RequestInit = {}
): Promise<Response> {
	const controller: AuthController = getAuthInstance();
	const csrfToken: string | null = controller.auth.csrfToken;
	const proxyAuthenticated: boolean = controller.auth.user?.authenticationSource === 'trusted_proxy';
	if (csrfToken === null && !proxyAuthenticated) {
		return fetch(input, init).then((response) => {
			if (response.status === 401) controller.markUnauthenticated();
			return response;
		});
	}
	const headers: Headers = new Headers(init.headers);
	if (csrfToken !== null) headers.set('X-SQLTide-CSRF', csrfToken);
	else if (proxyAuthenticated) {
		headers.set('X-SQLTide-CSRF', 'trusted-proxy');
	}
	return fetch(input, { ...init, headers }).then((response) => {
		if (response.status === 401) controller.markUnauthenticated();
		return response;
	});
}
