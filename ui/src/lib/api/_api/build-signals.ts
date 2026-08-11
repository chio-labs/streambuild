import { readApiResponse } from '$lib/api/_api/read-response';

export async function requestBuildCancellation(
	invocationId: string
): Promise<Record<string, unknown>> {
	return signalBuild('/api/build/cancel', invocationId);
}

export async function requestBuildKill(invocationId: string): Promise<Record<string, unknown>> {
	return signalBuild('/api/build/kill', invocationId);
}

async function signalBuild(path: string, invocationId: string): Promise<Record<string, unknown>> {
	const response: Response = await fetch(path, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ invocationId })
	});
	return readApiResponse<Record<string, unknown>>(response, 'build signal');
}
