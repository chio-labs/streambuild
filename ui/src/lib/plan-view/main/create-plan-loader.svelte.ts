import { fetchPlan } from '$lib/api/main/planning/fetch-plan';
import { getApp } from '$lib/api/main/project/get-app';
import type { AppState } from '$lib/api/types';
import type { Plan } from '$lib/planning/types';

type PlanLoadRequest = {
	selectors: string[];
	changed: boolean;
	includeMissingUpstream: boolean;
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
	readonly warehouseConnected: boolean;
	request(options: PlanLoadRequest): void;
	stop(): void;
};

export function createPlanLoader(options: PlanLoaderOptions): PlanLoader {
	const app: AppState = getApp();
	let plan = $state<Plan | null>(null);
	let error = $state<string | null>(null);
	let loading = $state<boolean>(true);
	let replayCountsLoading = $state<boolean>(false);
	let requestVersion: number = 0;
	let controller: AbortController | null = null;
	let latestRequest = $state<PlanLoadRequest | null>(null);
	let previousWarehouseConnected = $state<boolean | null>(null);
	const warehouseConnected: boolean = $derived(app.status?.warehouseConnected ?? false);

	function request(requestOptions: PlanLoadRequest): void {
		latestRequest = requestOptions;
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

	$effect(() => {
		const recovered: boolean = previousWarehouseConnected === false && warehouseConnected;
		previousWarehouseConnected = warehouseConnected;
		if (recovered && latestRequest !== null) request(latestRequest);
	});

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
		get warehouseConnected() {
			return warehouseConnected;
		},
		request,
		stop(): void {
			requestVersion += 1;
			controller?.abort();
		}
	};
}
