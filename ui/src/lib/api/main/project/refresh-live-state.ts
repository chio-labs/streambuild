import { getAppInstance } from '$lib/api/_helpers/app-instance.svelte';

export async function refreshLiveState(options?: { force?: boolean }): Promise<void> {
	await getAppInstance().refreshLiveState(options);
}
