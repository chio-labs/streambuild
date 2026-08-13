import { getAuthInstance } from '../_helpers/auth-instance.svelte';

export function logout(): Promise<void> {
	return getAuthInstance().logout();
}
