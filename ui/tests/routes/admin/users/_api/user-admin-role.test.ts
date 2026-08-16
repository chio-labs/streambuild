import { describe, expect, it, vi } from 'vitest';

const authenticatedFetch = vi.hoisted(() => vi.fn());
vi.mock('$lib/auth/main/authenticated-fetch', () => ({ authenticatedFetch }));

import { grantAdminRole } from '../../../../../src/routes/admin/users/_api/user-admin-role';
import type { AdminUser } from '../../../../../src/routes/admin/users/types';

describe('user role API', () => {
	it('given a viewer when granting admin then the decoded roles are returned', async () => {
		const user: AdminUser = { id: 'd0b46a1e-7553-47bd-9188-fcf59fbed050', username: 'alice', displayName: null, email: null, active: true, roles: ['admin', 'viewer'], authenticationSources: ['trusted_proxy'], createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z' };
		authenticatedFetch.mockResolvedValue(new Response(JSON.stringify(user)));

		await expect(grantAdminRole(user.id)).resolves.toMatchObject({ roles: ['admin', 'viewer'] });
	});
});
