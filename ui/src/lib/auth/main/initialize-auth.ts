import { getAuthInstance } from '../_helpers/auth-instance.svelte';

export function initializeAuth(): Promise<void> {
	return getAuthInstance().initialize();
}
