import { readApiResponse } from '$lib/api/_api/read-response';

type PlanRequestOptions = {
	selectors: string[];
	changed?: boolean;
	includeMissingUpstream?: boolean;
	startTime: string | null;
	deploymentId?: string | null;
	includeReplayCounts?: boolean;
	signal?: AbortSignal;
};

export async function requestPlan(options: PlanRequestOptions): Promise<Record<string, unknown>> {
	const params: URLSearchParams = new URLSearchParams();
	for (const selector of options.selectors) params.append('select', selector);
	if (options.changed) params.set('changed', 'true');
	if (options.includeMissingUpstream) params.set('include_missing_upstream', 'true');
	if (options.startTime !== null) params.set('start', options.startTime);
	if (options.deploymentId) params.set('deployment', options.deploymentId);
	if (options.includeReplayCounts) params.set('counts', 'true');
	const response: Response = await fetch(`/api/plan?${params}`, { signal: options.signal });
	return readApiResponse<Record<string, unknown>>(response, 'plan request');
}
