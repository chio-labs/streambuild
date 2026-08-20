import { getAppInstance } from '$lib/api/_helpers/app-instance.svelte';
import type { BootstrapPayload } from '$lib/api/types';

export function initializeAppFromBootstrap(payload: BootstrapPayload): void {
	getAppInstance().initializeFromBootstrap(payload);
}
