import { readApiResponse } from '$lib/api/_api/read-response';

type PlanRequestOptions = {
	selectors: string[];
	startTime: string | null;
	deploymentId?: string | null;
	includeReplayCounts?: boolean;
	signal?: AbortSignal;
};

export async function requestPlan(options: PlanRequestOptions): Promise<Record<string, unknown>> {
	const params: URLSearchParams = new URLSearchParams();
	for (const selector of options.selectors) params.append('select', selector);
	if (options.startTime !== null) params.set('start', options.startTime);
	if (options.deploymentId) params.set('deployment', options.deploymentId);
	if (options.includeReplayCounts) params.set('counts', 'true');
	const response: Response = await fetch(`/api/plan?${params}`, { signal: options.signal });
	return readApiResponse<Record<string, unknown>>(response, 'plan request');
}
