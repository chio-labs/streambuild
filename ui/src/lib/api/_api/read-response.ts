import { ApiError } from '$lib/api/errors';
import { markAuthUnauthenticated } from '$lib/auth/main/mark-auth-unauthenticated';

export async function readApiResponse<T>(response: Response, operation: string): Promise<T> {
	if (response.status === 401) markAuthUnauthenticated();
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
			} else if (payload.detail !== null && typeof payload.detail === 'object') {
				detail = structuredDetailMessage(payload.detail as Record<string, unknown>);
			}
		} catch {
			detail = body;
		}
	}
	return new ApiError(detail ?? `${operation} failed (${response.status})`, response.status);
}

function structuredDetailMessage(detail: Record<string, unknown>): string {
	const parts: string[] = [];
	if (typeof detail.message === 'string') parts.push(detail.message);
	if (typeof detail.permission === 'string') parts.push(`required permission: ${detail.permission}`);
	const missing: unknown = detail.missingPipelines;
	if (Array.isArray(missing) && missing.length > 0) {
		parts.push(`missing pipelines: ${missing.map(String).join(', ')}`);
	}
	if (typeof detail.target === 'string' && detail.target) parts.push(`target: ${detail.target}`);
	return parts.length > 0 ? parts.join(' — ') : JSON.stringify(detail);
}
