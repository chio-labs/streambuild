import { describe, expect, it, vi } from 'vitest';

const authenticatedFetch = vi.hoisted(() => vi.fn());
vi.mock('$lib/auth/main/authenticated-fetch', () => ({ authenticatedFetch }));

import { resetAdminUserPassword } from '../../../../../src/routes/admin/users/_api/user-password';

describe('user password API', () => {
	it('given a valid password reset when submitted then success is decoded', async () => {
		authenticatedFetch.mockResolvedValue(new Response('{"status":"ok"}'));

		await expect(resetAdminUserPassword('d0b46a1e-7553-47bd-9188-fcf59fbed050', 'long enough password')).resolves.toBeUndefined();
	});
});
