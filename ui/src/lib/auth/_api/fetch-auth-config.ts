import { authConfigSchema } from '../schemas';
import type { AuthConfig } from '../types';
import { readAuthResponse } from './read-auth-response';

export async function fetchAuthConfig(): Promise<AuthConfig> {
	return readAuthResponse(await fetch('/api/auth/config'), authConfigSchema, 'Read auth config');
}
