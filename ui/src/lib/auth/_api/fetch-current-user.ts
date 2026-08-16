import { authPayloadSchema } from '../schemas';
import type { AuthPayload } from '../types';
import { readAuthResponse } from './read-auth-response';

export async function fetchCurrentUser(): Promise<AuthPayload | null> {
	const response: Response = await fetch('/api/auth/me');
	if (response.status === 401) return null;
	return readAuthResponse(response, authPayloadSchema, 'Read current user');
}
