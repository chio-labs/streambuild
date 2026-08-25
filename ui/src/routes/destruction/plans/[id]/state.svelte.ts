import type { DestructionExecution, DestructionPlan } from '$lib/pipeline-view/types';
import { executeDestructionPlan } from '$lib/api/main/destruction/execute-destruction-plan';
import { fetchDestructionPlan } from '$lib/api/main/destruction/fetch-destruction-plan';
import { reviewDestructionPlan } from '$lib/api/main/destruction/review-destruction-plan';
import type { DestructionPlanPageState } from './types';

export function createDestructionPlanPageState(): DestructionPlanPageState {
	let plan = $state<DestructionPlan | null>(null);
	let requestedId = $state<string | null>(null);
	let responses = $state<string[]>([]);
	let loading = $state<boolean>(false);
	let reviewing = $state<boolean>(false);
	let executing = $state<boolean>(false);
	let error = $state<string | null>(null);
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

	async function load(planId: string): Promise<void> {
		controller?.abort();
		const nextController: AbortController = new AbortController();
		controller = nextController;
		const requestGeneration: number = ++generation;
		requestedId = planId;
		plan = null;
		responses = [];
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
		load,
		cancel,
		review,
		setResponse,
		execute
	};
}
