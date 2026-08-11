import { requestBuildCancellation } from '$lib/api/_api/build-signals';

export async function cancelBuild(invocationId: string): Promise<Record<string, unknown>> {
	return requestBuildCancellation(invocationId);
}
