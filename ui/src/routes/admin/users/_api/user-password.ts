import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';
import { usersOkStatusSchema } from '../schemas';
import { readUsersResponse } from './read-users-response';

export async function resetAdminUserPassword(userId: string, password: string): Promise<void> {
	const response: Response = await authenticatedFetch(
		`/api/admin/users/${encodeURIComponent(userId)}/password`,
		{
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ password })
		}
	);
	await readUsersResponse(response, usersOkStatusSchema, 'Reset password');
}
