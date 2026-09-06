import { requestInactivePipelines } from '../_api/request-inactive-pipelines';
import type { InactivePipeline } from '$lib/pipeline-view/types';

export async function getInactivePipelines(): Promise<InactivePipeline[]> {
	return requestInactivePipelines();
}
