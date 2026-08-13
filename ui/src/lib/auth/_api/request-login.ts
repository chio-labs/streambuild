import { authPayloadSchema } from '../schemas';
import type { AuthPayload } from '../types';
import { readAuthResponse } from './read-auth-response';

export async function requestLogin(username: string, password: string): Promise<AuthPayload> {
	const response: Response = await fetch('/api/auth/login', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ username, password })
	});
	return readAuthResponse(response, authPayloadSchema, 'Sign in');
}
