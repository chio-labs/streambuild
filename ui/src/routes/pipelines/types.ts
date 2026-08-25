import type {
	DestructionOperation,
	DestructionPlan
} from '$lib/pipeline-view/types';

export type PipelineModeFilter = 'all' | 'direct' | 'virtual';

export type DestructionController = {
	readonly selected: ReadonlySet<string>;
	readonly open: boolean;
	readonly operation: DestructionOperation | null;
	readonly plan: DestructionPlan | null;
	readonly planning: boolean;
	readonly error: string | null;
	togglePipeline(name: string): void;
	setCurrentPipelines(names: string[], checked: boolean): void;
	setOpen(open: boolean): void;
	start(operation: DestructionOperation): Promise<void>;
	addRequiredDependentsAndReplan(): Promise<void>;
};
