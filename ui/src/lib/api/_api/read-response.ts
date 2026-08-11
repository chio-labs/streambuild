import { ApiError } from '$lib/api/errors';

export async function readApiResponse<T>(response: Response, operation: string): Promise<T> {
	if (!response.ok) throw await responseError(response, operation);
	try {
		const body: string = await response.text();
		return JSON.parse(body) as T;
	} catch {
		throw new ApiError(`${operation} returned an invalid JSON response`, response.status);
	}
}

async function responseError(response: Response, operation: string): Promise<ApiError> {
	let body: string = '';
	try {
		body = (await response.text()).trim();
	} catch {
		body = '';
	}
	let detail: string | null = body || null;
	if (body) {
		try {
			const payload: { detail?: unknown } = JSON.parse(body) as { detail?: unknown };
			if (typeof payload.detail === 'string' && payload.detail.trim()) {
				detail = payload.detail.trim();
			}
		} catch {
			detail = body;
		}
	}
	return new ApiError(detail ?? `${operation} failed (${response.status})`, response.status);
}
