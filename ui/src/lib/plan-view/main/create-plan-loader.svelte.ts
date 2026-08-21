import { fetchPlan } from '$lib/api/main/planning/fetch-plan';
import type { Plan } from '$lib/planning/types';

type PlanLoadRequest = {
	selectors: string[];
	startTime: string | null;
	deploymentId: string | null;
	includeReplayCounts: boolean;
};

type PlanLoaderOptions = {
	onLoaded(plan: Plan, request: PlanLoadRequest): void;
};

type PlanLoader = {
	readonly plan: Plan | null;
	readonly error: string | null;
	readonly loading: boolean;
	readonly replayCountsLoading: boolean;
	request(options: PlanLoadRequest): void;
	stop(): void;
};

export function createPlanLoader(options: PlanLoaderOptions): PlanLoader {
	let plan = $state<Plan | null>(null);
	let error = $state<string | null>(null);
	let loading = $state<boolean>(true);
	let replayCountsLoading = $state<boolean>(false);
	let requestVersion: number = 0;
	let controller: AbortController | null = null;

	function request(requestOptions: PlanLoadRequest): void {
		const currentVersion: number = ++requestVersion;
		controller?.abort();
		controller = new AbortController();
		if (requestOptions.includeReplayCounts) replayCountsLoading = true;
		else loading = true;
		fetchPlan({ ...requestOptions, signal: controller.signal })
			.then((next: Plan) => {
				if (currentVersion !== requestVersion) return;
				plan = next;
				error = null;
				options.onLoaded(next, requestOptions);
			})
			.catch((caught: Error) => {
				if (currentVersion !== requestVersion || caught.name === 'AbortError') return;
				if (!requestOptions.includeReplayCounts) plan = null;
				error = caught.message;
			})
			.finally(() => {
				if (currentVersion !== requestVersion) return;
				if (requestOptions.includeReplayCounts) replayCountsLoading = false;
				else loading = false;
			});
	}

	return {
		get plan() {
			return plan;
		},
		get error() {
			return error;
		},
		get loading() {
			return loading;
		},
		get replayCountsLoading() {
			return replayCountsLoading;
		},
		request,
		stop(): void {
			requestVersion += 1;
			controller?.abort();
		}
	};
}
