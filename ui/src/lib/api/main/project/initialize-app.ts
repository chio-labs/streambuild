import { getAppInstance } from '$lib/api/_helpers/app-instance.svelte';

export async function initializeApp(): Promise<void> {
	await getAppInstance().initialize();
}
