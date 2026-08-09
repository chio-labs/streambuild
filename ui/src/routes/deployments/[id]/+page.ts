import { fetchDeployment } from '$lib/api';
import type { DeploymentDetail } from '$lib/domain/types';
import type { PageLoad } from './$types';

export type DeploymentDetailPageData = {
	initialDetail: DeploymentDetail | null;
	initialError: string | null;
};

/** Load on hover/navigation so the detail page never opens as an empty shell. */
export const load: PageLoad = async ({ params }): Promise<DeploymentDetailPageData> => {
	try {
		return { initialDetail: await fetchDeployment(params.id), initialError: null };
	} catch (error) {
		return {
			initialDetail: null,
			initialError: error instanceof Error ? error.message : String(error)
		};
	}
};
