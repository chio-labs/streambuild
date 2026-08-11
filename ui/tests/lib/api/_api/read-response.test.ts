import { describe, expect, it } from 'vitest';

import { readApiResponse } from '$lib/api/_api/read-response';
import { ApiError } from '$lib/api/errors';

describe('API response reader', () => {
	it('given a successful JSON response when read then its body is returned', async () => {
		const response: Response = new Response('{"value":42}');
		const result: { value: number } = await readApiResponse<{ value: number }>(response, 'example');

		expect(result).toEqual({ value: 42 });
	});

	it('given a failed JSON response when read then its detail and status become an API error', async () => {
		const response: Response = new Response('{"detail":"not ready"}', { status: 409 });
		const error: ApiError = await readApiResponse<never>(response, 'example').catch(
			(reason: unknown): ApiError => reason as ApiError
		);

		expect(error).toBeInstanceOf(ApiError);
		expect(error.message).toBe('not ready');
		expect(error.status).toBe(409);
	});
});
