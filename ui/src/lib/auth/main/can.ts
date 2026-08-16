import { getAuthInstance } from '../_helpers/auth-instance.svelte';
import { hasCapability } from '../_helpers/permission-checks';

export function can(permission: string, pipeline?: string): boolean {
	return hasCapability(getAuthInstance().auth.capabilities, permission, pipeline);
}
