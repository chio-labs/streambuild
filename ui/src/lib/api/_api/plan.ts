import { readApiResponse } from '$lib/api/_api/read-response';

export async function requestPlan(
	selectors: string[],
	startTime: string | null
): Promise<Record<string, unknown>> {
	const params: URLSearchParams = new URLSearchParams();
	for (const selector of selectors) params.append('select', selector);
	if (startTime !== null) params.set('start', startTime);
	const response: Response = await fetch(`/api/plan?${params}`);
	return readApiResponse<Record<string, unknown>>(response, 'plan request');
}
