import { getAppInstance } from '$lib/api/_helpers/app-instance.svelte';

export async function refreshLiveState(): Promise<void> {
	await getAppInstance().refreshLiveState();
}
