import type { DestructionOperation } from '$lib/pipeline-view/types';

export function destructionOperationLabel(operation: DestructionOperation): string {
	return operation === 'reset_target' ? 'Reset target' : 'Destroy pipelines';
}

export function formatPlanTimestamp(value: string): string {
	const date: Date = new Date(value);
	return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
