import { createAuthState } from '../_state/auth.state.svelte';
import type { AuthController } from '../types';

let instance: AuthController | undefined;

export function getAuthInstance(): AuthController {
	instance ??= createAuthState();
	return instance;
}
