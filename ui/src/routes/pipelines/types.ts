import type {
	DestructionExecution,
	DestructionOperation,
	DestructionPlan,
	ReviewedDestructionPlan
} from '$lib/pipeline-view/types';

export type DestructionController = {
	readonly selected: ReadonlySet<string>;
	readonly open: boolean;
	readonly operation: DestructionOperation | null;
	readonly plan: DestructionPlan | ReviewedDestructionPlan | null;
	readonly responses: readonly string[];
	readonly planning: boolean;
	readonly reviewing: boolean;
	readonly executing: boolean;
	readonly error: string | null;
	readonly reviewed: boolean;
	readonly canExecute: boolean;
	togglePipeline(name: string): void;
	setCurrentPipelines(names: string[], checked: boolean): void;
	setOpen(open: boolean): void;
	start(operation: DestructionOperation): Promise<void>;
	addRequiredDependentsAndReplan(): Promise<void>;
	review(): Promise<void>;
	setResponse(index: number, value: string): void;
	execute(): Promise<DestructionExecution | null>;
};
