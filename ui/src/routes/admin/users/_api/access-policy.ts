import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';
import { accessPolicySchema } from '../schemas';
import type { AccessPolicy } from '../types';
import { readUsersResponse } from './read-users-response';

export async function fetchAccessPolicy(): Promise<AccessPolicy> {
	const response: Response = await authenticatedFetch('/api/access-policy');
	return readUsersResponse(response, accessPolicySchema, 'Read access policy');
}
