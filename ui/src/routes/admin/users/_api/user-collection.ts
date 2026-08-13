import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';
import { adminUserSchema, adminUsersSchema } from '../schemas';
import type { AdminUser, CreateAdminUserInput } from '../types';
import { readUsersResponse } from './read-users-response';

export async function fetchAdminUsers(): Promise<AdminUser[]> {
	return readUsersResponse(
		await authenticatedFetch('/api/admin/users'),
		adminUsersSchema,
		'List users'
	);
}

export async function createAdminUser(input: CreateAdminUserInput): Promise<AdminUser> {
	const response: Response = await authenticatedFetch('/api/admin/users', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(input)
	});
	return readUsersResponse(response, adminUserSchema, 'Create user');
}
