import { readApiResponse } from '$lib/api/_api/read-response';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';

export async function requestBuildCancellation(
	invocationId: string
): Promise<Record<string, unknown>> {
	return signalBuild('/api/build/cancel', invocationId);
}

export async function requestBuildKill(invocationId: string): Promise<Record<string, unknown>> {
	return signalBuild('/api/build/kill', invocationId);
}

async function signalBuild(path: string, invocationId: string): Promise<Record<string, unknown>> {
	const response: Response = await authenticatedFetch(path, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ invocationId })
	});
	return readApiResponse<Record<string, unknown>>(response, 'build signal');
}
