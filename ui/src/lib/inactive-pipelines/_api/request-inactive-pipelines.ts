import { readApiResponse } from '$lib/api/main/response/read-api-response';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';
import type { InactivePipeline } from '$lib/pipeline-view/types';

type InactivePipelinesResponse = {
	pipelines: InactivePipeline[];
};

export async function requestInactivePipelines(): Promise<InactivePipeline[]> {
	const response: Response = await authenticatedFetch('/api/destruction/pipelines/inactive');
	const payload: InactivePipelinesResponse = await readApiResponse<InactivePipelinesResponse>(
		response,
		'inactive pipelines'
	);
	return payload.pipelines;
}
