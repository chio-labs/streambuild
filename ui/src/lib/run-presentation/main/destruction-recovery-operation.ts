import type { DestructionOperation } from '$lib/pipeline-view/types';

export function destructionRecoveryOperation(
	outcome: string,
	command: string | null,
	mode: string | null
): DestructionOperation | null {
	if (outcome !== 'failed' || mode !== 'destructive') return null;
	if (command === 'destroy pipelines') return 'destroy_pipelines';
	if (command === 'reset target') return 'reset_target';
	return null;
}
