import { getAppInstance } from '$lib/api/_helpers/app-instance.svelte';
import type { AppState } from '$lib/api/types';

export function getApp(): AppState {
	return getAppInstance().app;
}
