import { describe, expect, it } from 'vitest';

import { adminUserSchema } from '../../../../../src/routes/admin/users/schemas';
import { readUsersResponse } from '../../../../../src/routes/admin/users/_api/read-users-response';

describe('users response reader', () => {
	it('given malformed account JSON when read then runtime decoding rejects it', async () => {
		await expect(readUsersResponse(new Response('{"id":1}'), adminUserSchema, 'Read user')).rejects.toThrow();
	});
});
