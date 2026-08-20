import { requestBootstrapPayload } from '$lib/api/_api/bootstrap';
import type { BootstrapPayload } from '$lib/api/types';
import { getAuth } from '$lib/auth/main/get-auth';
import { initializeAuth } from '$lib/auth/main/initialize-auth';
import { initializeAuthFromBootstrap } from '$lib/auth/main/initialize-auth-from-bootstrap';
import { initializeApp } from '$lib/api/main/project/initialize-app';
import { initializeAppFromBootstrap } from '$lib/api/main/project/_initialize-app-from-bootstrap';

export async function initializeBootstrap(): Promise<void> {
	let bootstrap: BootstrapPayload | null;
	try {
		bootstrap = await requestBootstrapPayload();
	} catch {
		bootstrap = null;
	}
	if (bootstrap === null) {
		await initializeAuth();
		if (getAuth().phase === 'authenticated') await initializeApp();
		return;
	}
	initializeAuthFromBootstrap(
		bootstrap.auth.config,
		bootstrap.auth.session,
		bootstrap.auth.capabilities
	);
	initializeAppFromBootstrap(bootstrap);
}
