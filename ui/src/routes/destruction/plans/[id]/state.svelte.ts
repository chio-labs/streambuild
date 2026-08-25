import type {
	DestructionExecution,
	DestructionPlan,
	DestructionResource
} from '$lib/pipeline-view/types';
import { executeDestructionPlan } from '$lib/api/main/destruction/execute-destruction-plan';
import { fetchDestructionPlan } from '$lib/api/main/destruction/fetch-destruction-plan';
import { reviewDestructionPlan } from '$lib/api/main/destruction/review-destruction-plan';
import type { DestructionPlanPageState, ResourcePageSize } from './types';

const MODEL_PREVIEW_LIMIT: number = 48;

export function createDestructionPlanPageState(): DestructionPlanPageState {
	let plan = $state<DestructionPlan | null>(null);
	let requestedId = $state<string | null>(null);
	let responses = $state<string[]>([]);
	let loading = $state<boolean>(false);
	let reviewing = $state<boolean>(false);
	let executing = $state<boolean>(false);
	let error = $state<string | null>(null);
	let modelsExpanded = $state<boolean>(false);
	let resourcePage = $state<number>(1);
	let resourcePageSize = $state<ResourcePageSize>(25);
	let controller: AbortController | null = null;
	let generation: number = 0;
	const reviewed: boolean = $derived(plan?.reviewedAt !== null && plan?.reviewedAt !== undefined);
	const canExecute: boolean = $derived.by(() => {
		if (plan === null || !reviewed || plan.blocked) return false;
		return (
			plan.challengeValues.length === responses.length &&
			plan.challengeValues.every((challenge, index) => responses[index] === challenge)
		);
	});
	const visibleModels: readonly string[] = $derived(
		plan === null || modelsExpanded ? (plan?.models ?? []) : plan.models.slice(0, MODEL_PREVIEW_LIMIT)
	);
	const resourcePageCount: number = $derived(
		Math.max(1, Math.ceil((plan?.resources.length ?? 0) / resourcePageSize))
	);
	const resourceFirst: number = $derived(
		plan === null || plan.resources.length === 0 ? 0 : (resourcePage - 1) * resourcePageSize + 1
	);
	const resourceLast: number = $derived(
		Math.min(resourcePage * resourcePageSize, plan?.resources.length ?? 0)
	);
	const visibleResources: readonly DestructionResource[] = $derived(
		plan?.resources.slice(resourceFirst === 0 ? 0 : resourceFirst - 1, resourceLast) ?? []
	);
	const existingResourceCount: number = $derived(
		plan?.resources.filter((resource: DestructionResource) => resource.exists).length ?? 0
	);
	const absentResourceCount: number = $derived(
		(plan?.resources.length ?? 0) - existingResourceCount
	);

	async function load(planId: string): Promise<void> {
		controller?.abort();
		const nextController: AbortController = new AbortController();
		controller = nextController;
		const requestGeneration: number = ++generation;
		requestedId = planId;
		plan = null;
		responses = [];
		modelsExpanded = false;
		resourcePage = 1;
		error = null;
		loading = true;
		try {
			const stored: DestructionPlan = await fetchDestructionPlan(planId, nextController.signal);
			if (generation === requestGeneration) {
				plan = stored;
				responses = stored.reviewedAt === null ? [] : stored.challengeValues.map(() => '');
			}
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

	async function review(): Promise<void> {
		if (plan === null || plan.blocked) return;
		reviewing = true;
		error = null;
		try {
			plan = await reviewDestructionPlan(plan.planId);
			responses = plan.challengeValues.map(() => '');
		} catch (caught) {
			error = caught instanceof Error ? caught.message : String(caught);
		} finally {
			reviewing = false;
		}
	}

	function setResponse(index: number, value: string): void {
		responses = responses.map((response, responseIndex) =>
			responseIndex === index ? value : response
		);
	}

	function toggleModels(): void {
		modelsExpanded = !modelsExpanded;
	}

	function setResourcePage(nextPage: number): void {
		resourcePage = Math.min(Math.max(1, nextPage), resourcePageCount);
	}

	function setResourcePageSize(size: ResourcePageSize): void {
		resourcePageSize = size;
		resourcePage = 1;
	}

	async function execute(): Promise<DestructionExecution | null> {
		if (plan === null || !canExecute) return null;
		executing = true;
		error = null;
		try {
			return await executeDestructionPlan(plan.planId, [...responses]);
		} catch (caught) {
			error = caught instanceof Error ? caught.message : String(caught);
			return null;
		} finally {
			executing = false;
		}
	}

	return {
		get plan() {
			return plan;
		},
		get requestedId() {
			return requestedId;
		},
		get responses() {
			return responses;
		},
		get loading() {
			return loading;
		},
		get reviewing() {
			return reviewing;
		},
		get executing() {
			return executing;
		},
		get error() {
			return error;
		},
		get reviewed() {
			return reviewed;
		},
		get canExecute() {
			return canExecute;
		},
		modelList: {
			get expanded() {
				return modelsExpanded;
			},
			get visible() {
				return visibleModels;
			},
			toggle: toggleModels
		},
		resourceList: {
			get page() {
				return resourcePage;
			},
			get pageSize() {
				return resourcePageSize;
			},
			get pageCount() {
				return resourcePageCount;
			},
			get first() {
				return resourceFirst;
			},
			get last() {
				return resourceLast;
			},
			get visible() {
				return visibleResources;
			},
			get existingCount() {
				return existingResourceCount;
			},
			get absentCount() {
				return absentResourceCount;
			},
			setPage: setResourcePage,
			setPageSize: setResourcePageSize
		},
		load,
		cancel,
		review,
		setResponse,
		execute
	};
}
