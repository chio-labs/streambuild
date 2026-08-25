import { goto } from '$app/navigation';
import {
	createDestructionPlan
} from '$lib/api/main/destruction/create-destruction-plan';
import type {
	DestructionOperation,
	DestructionPlan
} from '$lib/pipeline-view/types';
import type { DestructionController } from './types';

export function createDestructionState(): DestructionController {
	let selected = $state<ReadonlySet<string>>(new Set());
	let open = $state<boolean>(false);
	let operation = $state<DestructionOperation | null>(null);
	let plan = $state<DestructionPlan | null>(null);
	let planning = $state<boolean>(false);
	let error = $state<string | null>(null);

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
		if (!value && planning) return;
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
		error = null;
		try {
			const created: DestructionPlan = await createDestructionPlan(
				nextOperation,
				pipelineNames,
				includedDependentPipelineNames
			);
			plan = created;
			if (created.blocked) {
				return;
			}
			await goto(`/destruction/plans/${encodeURIComponent(created.planId)}`);
			open = false;
			resetPlan();
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

	function resetPlan(): void {
		operation = null;
		plan = null;
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
		get planning() {
			return planning;
		},
		get error() {
			return error;
		},
		togglePipeline,
		setCurrentPipelines,
		setOpen,
		start,
		addRequiredDependentsAndReplan
	};
}
