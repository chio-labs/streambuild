import { goto } from '$app/navigation';

export async function openRun(invocationId: string): Promise<void> {
	await goto(`/runs/${invocationId}?live=1`);
}
