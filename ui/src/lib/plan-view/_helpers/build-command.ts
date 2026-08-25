import { selectorToken } from '$lib/planning/main/selector-token';
import { replayStartToken } from '$lib/plan-view/_helpers/plan-location';
import type { BuildCommandParts } from '$lib/plan-view/types';

/**
 * Compose the `stb build …` command straight from local selection state so the
 * displayed command tracks edits instantly, without waiting on the server plan.
 * The deployment id only lands once the server resolves a virtual/mixed plan, so
 * it is held back while a re-plan is in flight; a direct build never carries one.
 */
export function buildPlanCommand(parts: BuildCommandParts): string {
	const tokens: string[] = parts.selectors.map(selectorToken);
	const start: string | null = replayStartToken(parts.replayWindow);
	const resolved: boolean = !parts.planLoading && parts.plan !== null;
	const deploymentId: string | null = resolved ? (parts.plan?.deploymentId ?? null) : null;
	const segments: string[] = ['stb build'];
	if (parts.changed) segments.push('--changed');
	else if (tokens.length > 0) segments.push(`--select ${tokens.join(' ')}`);
	if (parts.includeMissingUpstream) segments.push('--include-missing-upstream');
	if (start !== null) segments.push(`--start-time ${start}`);
	if (deploymentId !== null) segments.push(`--deployment-id ${deploymentId}`);
	for (const value of parts.acceptedConfirmations) segments.push(`--confirm ${value}`);
	return segments.join(' ');
}
