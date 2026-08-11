import { getAppInstance } from '$lib/api/_helpers/app-instance.svelte';

export async function reloadProject(): Promise<void> {
	await getAppInstance().reload();
}
