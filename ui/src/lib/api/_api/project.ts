import { readApiResponse } from '$lib/api/_api/read-response';

export async function requestStatusPayload(): Promise<Record<string, unknown>> {
	const response: Response = await fetch('/api/status');
	return readApiResponse<Record<string, unknown>>(response, 'status');
}

export async function requestDefinitionsPayload(): Promise<Record<string, unknown>> {
	const response: Response = await fetch('/api/definitions');
	return readApiResponse<Record<string, unknown>>(response, 'definitions');
}

export async function requestStatePayload(): Promise<Record<string, unknown> | null> {
	const response: Response = await fetch('/api/state');
	if (!response.ok) return null;
	return readApiResponse<Record<string, unknown>>(response, 'state');
}
