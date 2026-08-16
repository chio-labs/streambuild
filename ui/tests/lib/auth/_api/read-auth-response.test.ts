import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import { readAuthResponse } from '$lib/auth/_api/read-auth-response';

describe('auth response reader', () => {
	it('given malformed success JSON when read then runtime decoding rejects it', async () => {
		const response: Response = new Response('{"value":"wrong"}');

		await expect(readAuthResponse(response, z.object({ value: z.number() }), 'Read value')).rejects.toThrow();
	});
});
