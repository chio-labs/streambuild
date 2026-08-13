import { describe, expect, it, vi } from 'vitest';

const requests = vi.hoisted(() => ({ fetchAdminUsers: vi.fn() }));
vi.mock('../../../../../src/routes/admin/users/_api/user-collection', () => ({
	fetchAdminUsers: requests.fetchAdminUsers,
	createAdminUser: vi.fn()
}));

import { createUsersAdminState } from '../../../../../src/routes/admin/users/_state/users-admin.state.svelte';
import type { UsersAdminController } from '../../../../../src/routes/admin/users/types';

describe('users admin state', () => {
	it('given accounts when loaded then the state exposes them', async () => {
		requests.fetchAdminUsers.mockResolvedValue([]);
		const controller: UsersAdminController = createUsersAdminState();

		await controller.load();

		expect(controller.state.users).toEqual([]);
		expect(controller.state.loading).toBe(false);
	});
});
