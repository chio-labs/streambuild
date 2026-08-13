import type { Capabilities } from '../types';

export function hasCapability(
	capabilities: Capabilities | null,
	permission: string,
	pipeline?: string
): boolean {
	if (capabilities === null) return false;
	if (capabilities.systemAdmin) return true;
	if (pipeline === undefined) return capabilities.permissions.includes(permission);
	const pipelines: string[] = capabilities.pipelinePermissions[permission] ?? [];
	return pipelines.includes(pipeline);
}

export function hasAnyPipelineCapability(
	capabilities: Capabilities | null,
	permission: string
): boolean {
	if (capabilities === null) return false;
	if (capabilities.systemAdmin) return true;
	return (capabilities.pipelinePermissions[permission] ?? []).length > 0;
}
