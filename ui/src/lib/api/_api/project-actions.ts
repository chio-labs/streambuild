import { readApiResponse } from '$lib/api/_api/read-response';

export async function requestProjectReload(): Promise<Record<string, unknown>> {
	const response: Response = await fetch('/api/reload', { method: 'POST' });
	return readApiResponse<Record<string, unknown>>(response, 'project reload');
}
