import { getAuthInstance } from '../_helpers/auth-instance.svelte';
import type { AuthState } from '../types';

export function getAuth(): AuthState {
	return getAuthInstance().auth;
}
