import { readApiResponse } from '$lib/api/_api/read-response';

export async function requestStatusPayload(signal?: AbortSignal): Promise<Record<string, unknown>> {
	const response: Response = await fetch('/api/status', { signal });
	return readApiResponse<Record<string, unknown>>(response, 'status');
}

export async function requestDefinitionsPayload(
	versionKey?: string,
	signal?: AbortSignal
): Promise<Record<string, unknown>> {
	const cacheKey: string | null = versionKey ? `streambuild:definitions:${versionKey}` : null;
	let cached: Record<string, unknown> | null = null;
	if (cacheKey !== null && typeof sessionStorage !== 'undefined') {
		try {
			const stored: string | null = sessionStorage.getItem(cacheKey);
			if (stored !== null) cached = JSON.parse(stored) as Record<string, unknown>;
		} catch {
			cached = null;
		}
	}
	const headers: HeadersInit | undefined =
		versionKey && cached !== null ? { 'If-None-Match': `"${versionKey}"` } : undefined;
	const response: Response = await fetch('/api/definitions', { headers, signal });
	if (response.status === 304 && cached !== null) return cached;
	const definitions: Record<string, unknown> = await readApiResponse<Record<string, unknown>>(
		response,
		'definitions'
	);
	if (cacheKey !== null && typeof sessionStorage !== 'undefined') {
		try {
			pruneDefinitionsCache(cacheKey);
			sessionStorage.setItem(cacheKey, JSON.stringify(definitions));
		} catch {
			// Definitions caching is optional; browser storage quotas must not block startup.
		}
	}
	return definitions;
}

function pruneDefinitionsCache(currentKey: string): void {
	for (let index: number = sessionStorage.length - 1; index >= 0; index -= 1) {
		const key: string | null = sessionStorage.key(index);
		if (key?.startsWith('streambuild:definitions:') && key !== currentKey) {
			sessionStorage.removeItem(key);
		}
	}
}

export async function requestStatePayload(signal?: AbortSignal): Promise<Record<string, unknown> | null> {
	const response: Response = await fetch('/api/state', { signal });
	if (!response.ok) return null;
	return readApiResponse<Record<string, unknown>>(response, 'state');
}
