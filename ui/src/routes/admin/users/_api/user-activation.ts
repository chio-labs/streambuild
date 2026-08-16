import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';
import { adminUserSchema } from '../schemas';
import type { AdminUser } from '../types';
import { readUsersResponse } from './read-users-response';

export async function setAdminUserActive(userId: string, active: boolean): Promise<AdminUser> {
	const response: Response = await authenticatedFetch(
		`/api/admin/users/${encodeURIComponent(userId)}`,
		{
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ active })
		}
	);
	return readUsersResponse(response, adminUserSchema, 'Update user');
}
