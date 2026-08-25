import type { DestructionOperation } from '$lib/pipeline-view/types';

export function destructionOperationLabel(operation: DestructionOperation): string {
	return operation === 'reset_target' ? 'Reset target' : 'Destroy pipelines';
}
