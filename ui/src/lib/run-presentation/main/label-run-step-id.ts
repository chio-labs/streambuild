import { labelRunStepId as buildLabel } from '$lib/run-presentation/_helpers/run-event-label';

export function labelRunStepId(stepId: string): string {
	return buildLabel(stepId);
}
