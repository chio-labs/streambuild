import { readApiResponse } from '$lib/api/_api/read-response';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';

export async function requestProjectReload(): Promise<Record<string, unknown>> {
	const response: Response = await authenticatedFetch('/api/reload', { method: 'POST' });
	return readApiResponse<Record<string, unknown>>(response, 'project reload');
}

export async function requestWarehouseRefresh(signal?: AbortSignal): Promise<Record<string, unknown>> {
	const response: Response = await authenticatedFetch('/api/warehouse/refresh', {
		method: 'POST',
		signal
	});
	return readApiResponse<Record<string, unknown>>(response, 'warehouse refresh');
}
