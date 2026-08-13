import { describe, expect, it, vi } from 'vitest';

const authenticatedFetch = vi.hoisted(() => vi.fn());
vi.mock('$lib/auth/main/authenticated-fetch', () => ({ authenticatedFetch }));

import { fetchAdminUsers } from '../../../../../src/routes/admin/users/_api/user-collection';

describe('users collection API', () => {
	it('given no accounts when listed then an empty decoded collection is returned', async () => {
		authenticatedFetch.mockResolvedValue(new Response('[]'));

		await expect(fetchAdminUsers()).resolves.toEqual([]);
	});
});
