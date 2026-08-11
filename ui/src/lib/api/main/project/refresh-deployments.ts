import { getAppInstance } from '$lib/api/_helpers/app-instance.svelte';

export async function refreshDeployments(): Promise<void> {
	await getAppInstance().refreshDeployments();
}
