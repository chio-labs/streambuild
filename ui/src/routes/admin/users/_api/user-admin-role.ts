import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';
import { adminUserSchema } from '../schemas';
import type { AdminUser } from '../types';
import { readUsersResponse } from './read-users-response';

export async function grantAdminRole(userId: string): Promise<AdminUser> {
	const response: Response = await authenticatedFetch(
		`/api/admin/users/${encodeURIComponent(userId)}/roles`,
		{
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ role: 'admin' })
		}
	);
	return readUsersResponse(response, adminUserSchema, 'Grant administrator');
}

export async function revokeAdminRole(userId: string): Promise<AdminUser> {
	const response: Response = await authenticatedFetch(
		`/api/admin/users/${encodeURIComponent(userId)}/roles/admin`,
		{ method: 'DELETE' }
	);
	return readUsersResponse(response, adminUserSchema, 'Revoke administrator');
}
