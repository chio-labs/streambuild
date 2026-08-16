import { capabilitiesSchema } from '../schemas';
import type { Capabilities } from '../types';
import { readAuthResponse } from './read-auth-response';

export async function fetchCapabilities(): Promise<Capabilities | null> {
	const response: Response = await fetch('/api/auth/capabilities');
	if (response.status === 401 || response.status === 404) return null;
	return readAuthResponse(response, capabilitiesSchema, 'Read capabilities');
}
