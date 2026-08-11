import { requestBuildKill } from '$lib/api/_api/build-signals';

export async function killBuild(invocationId: string): Promise<Record<string, unknown>> {
	return requestBuildKill(invocationId);
}
