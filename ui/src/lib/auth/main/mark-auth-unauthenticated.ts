import { getAuthInstance } from '../_helpers/auth-instance.svelte';

export function markAuthUnauthenticated(): void {
	getAuthInstance().markUnauthenticated();
}
