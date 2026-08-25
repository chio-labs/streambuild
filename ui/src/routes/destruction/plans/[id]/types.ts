import type { DestructionExecution, DestructionPlan } from '$lib/pipeline-view/types';

export type DestructionPlanPageState = {
	readonly plan: DestructionPlan | null;
	readonly requestedId: string | null;
	readonly responses: readonly string[];
	readonly loading: boolean;
	readonly reviewing: boolean;
	readonly executing: boolean;
	readonly error: string | null;
	readonly reviewed: boolean;
	readonly canExecute: boolean;
	load(planId: string): Promise<void>;
	cancel(): void;
	review(): Promise<void>;
	setResponse(index: number, value: string): void;
	execute(): Promise<DestructionExecution | null>;
};
