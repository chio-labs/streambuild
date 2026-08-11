import { createAppState } from '$lib/api/_state/app.state.svelte';
import type { AppController } from '$lib/api/types';

let instance: AppController | null = null;

export function getAppInstance(): AppController {
	if (instance === null) instance = createAppState();
	return instance;
}
