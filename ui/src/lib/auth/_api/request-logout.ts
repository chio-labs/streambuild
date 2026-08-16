import { authOkStatusSchema } from '../schemas';
import { readAuthResponse } from './read-auth-response';

export async function requestLogout(csrfToken: string | null): Promise<void> {
	const response: Response = await fetch('/api/auth/logout', {
		method: 'POST',
		headers: csrfToken === null ? {} : { 'X-StreamBuild-CSRF': csrfToken }
	});
	await readAuthResponse(response, authOkStatusSchema, 'Sign out');
}
