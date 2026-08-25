import { labelRunPhase as buildLabel } from '$lib/run-presentation/_helpers/run-phase-label';

export function labelRunPhase(phase: string | null): string {
	return buildLabel(phase);
}
