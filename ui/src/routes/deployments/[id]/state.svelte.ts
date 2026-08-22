import { fetchDeployment } from '$lib/api/main/deployments/fetch-deployment';
import type { DeploymentDetail } from '$lib/domain/types';
import type { DeploymentDetailState } from './types';

export function createDeploymentDetailState(): DeploymentDetailState {
	let detail = $state<DeploymentDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state<boolean>(false);
	let requestedId = $state<string | null>(null);
	let controller: AbortController | null = null;
	let generation: number = 0;

	async function load(deploymentId: string): Promise<void> {
		controller?.abort();
		const nextController: AbortController = new AbortController();
		controller = nextController;
		const requestGeneration: number = ++generation;
		requestedId = deploymentId;
		detail = null;
		error = null;
		loading = true;
		try {
			const next: DeploymentDetail = await fetchDeployment(deploymentId, nextController.signal);
			if (generation === requestGeneration) detail = next;
		} catch (caught) {
			if (generation === requestGeneration && !nextController.signal.aborted) {
				error = caught instanceof Error ? caught.message : String(caught);
			}
		} finally {
			if (generation === requestGeneration) loading = false;
		}
	}

	function cancel(): void {
		generation += 1;
		controller?.abort();
		loading = false;
	}

	return {
		get detail() {
			return detail;
		},
		get error() {
			return error;
		},
		get loading() {
			return loading;
		},
		get requestedId() {
			return requestedId;
		},
		load,
		cancel
	};
}
