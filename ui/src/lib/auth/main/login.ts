import { getAuthInstance } from '../_helpers/auth-instance.svelte';

export function login(username: string, password: string): Promise<void> {
	return getAuthInstance().login(username, password);
}
