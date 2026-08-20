import { getAuthInstance } from '../_helpers/auth-instance.svelte';
import type { AuthConfig, AuthPayload, Capabilities } from '../types';

export function initializeAuthFromBootstrap(
	config: AuthConfig,
	payload: AuthPayload,
	capabilities: Capabilities | null
): void {
	getAuthInstance().initializeFromBootstrap(config, payload, capabilities);
}
