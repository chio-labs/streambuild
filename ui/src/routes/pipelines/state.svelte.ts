import {
	createDestructionPlan
} from '$lib/api/main/destruction/create-destruction-plan';
import { executeDestructionPlan } from '$lib/api/main/destruction/execute-destruction-plan';
import { reviewDestructionPlan } from '$lib/api/main/destruction/review-destruction-plan';
import type {
	DestructionExecution,
	DestructionOperation,
	DestructionPlan,
	ReviewedDestructionPlan
} from '$lib/pipeline-view/types';
import type { DestructionController } from './types';

export function createDestructionState(): DestructionController {
	let selected = $state<ReadonlySet<string>>(new Set());
	let open = $state<boolean>(false);
	let operation = $state<DestructionOperation | null>(null);
	let plan = $state<DestructionPlan | ReviewedDestructionPlan | null>(null);
	let responses = $state<string[]>([]);
	let planning = $state<boolean>(false);
	let reviewing = $state<boolean>(false);
	let executing = $state<boolean>(false);
	let error = $state<string | null>(null);
	const reviewed: boolean = $derived(plan !== null && 'reviewedAt' in plan);
	const canExecute: boolean = $derived.by(() => {
		if (plan === null || !reviewed || plan.blocked) return false;
		return (
			plan.challengeValues.length === responses.length &&
			plan.challengeValues.every((challenge, index) => responses[index] === challenge)
		);
	});

	function togglePipeline(name: string): void {
		const next: Set<string> = new Set(selected);
		if (next.has(name)) next.delete(name);
		else next.add(name);
		selected = next;
	}

	function setCurrentPipelines(names: string[], checked: boolean): void {
		const next: Set<string> = new Set(selected);
		for (const name of names) {
			if (checked) next.add(name);
			else next.delete(name);
		}
		selected = next;
	}

	function setOpen(value: boolean): void {
		if (!value && (planning || reviewing || executing)) return;
		open = value;
		if (!value) resetPlan();
	}

	async function start(nextOperation: DestructionOperation): Promise<void> {
		open = true;
		operation = nextOperation;
		await loadPlan(
			nextOperation,
			nextOperation === 'destroy_pipelines' ? [...selected].sort() : [],
			[]
		);
	}

	async function loadPlan(
		nextOperation: DestructionOperation,
		pipelineNames: string[],
		includedDependentPipelineNames: string[]
	): Promise<void> {
		planning = true;
		plan = null;
		responses = [];
		error = null;
		try {
			plan = await createDestructionPlan(
				nextOperation,
				pipelineNames,
				includedDependentPipelineNames
			);
		} catch (caught) {
			error = String(caught);
		} finally {
			planning = false;
		}
	}

	async function addRequiredDependentsAndReplan(): Promise<void> {
		if (plan === null || operation !== 'destroy_pipelines') return;
		const next: Set<string> = new Set(selected);
		for (const pipelineName of plan.requiredDependentPipelines) next.add(pipelineName);
		selected = next;
		await loadPlan(
			operation,
			[...plan.selectedPipelines].sort(),
			[...plan.requiredDependentPipelines].sort()
		);
	}

	async function review(): Promise<void> {
		if (plan === null || plan.blocked) return;
		reviewing = true;
		error = null;
		try {
			plan = await reviewDestructionPlan(plan.planId);
			responses = plan.challengeValues.map(() => '');
		} catch (caught) {
			error = String(caught);
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
			error = String(caught);
			return null;
		} finally {
			executing = false;
		}
	}

	function resetPlan(): void {
		operation = null;
		plan = null;
		responses = [];
		error = null;
	}

	return {
		get selected() {
			return selected;
		},
		get open() {
			return open;
		},
		get operation() {
			return operation;
		},
		get plan() {
			return plan;
		},
		get responses() {
			return responses;
		},
		get planning() {
			return planning;
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
		togglePipeline,
		setCurrentPipelines,
		setOpen,
		start,
		addRequiredDependentsAndReplan,
		review,
		setResponse,
		execute
	};
}
