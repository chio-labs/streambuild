import { describe, expect, it, vi } from 'vitest';

const authenticatedFetch = vi.hoisted(() => vi.fn());
vi.mock('$lib/auth/main/authenticated-fetch', () => ({ authenticatedFetch }));

import { setAdminUserActive } from '../../../../../src/routes/admin/users/_api/user-activation';
import type { AdminUser } from '../../../../../src/routes/admin/users/types';

describe('user activation API', () => {
	it('given an account when disabling then the decoded account is returned', async () => {
		const user: AdminUser = { id: 'd0b46a1e-7553-47bd-9188-fcf59fbed050', username: 'alice', displayName: null, email: null, active: false, roles: ['viewer'], authenticationSources: ['trusted_proxy'], createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z' };
		authenticatedFetch.mockResolvedValue(new Response(JSON.stringify(user)));

		await expect(setAdminUserActive(user.id, false)).resolves.toMatchObject({ active: false });
	});
});
