import { getAuthInstance } from '../_helpers/auth-instance.svelte';
import { hasAnyPipelineCapability } from '../_helpers/permission-checks';

export function canAnyPipeline(permission: string): boolean {
	return hasAnyPipelineCapability(getAuthInstance().auth.capabilities, permission);
}
