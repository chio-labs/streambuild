import type {
	DestructionOperation,
	DestructionPlan
} from '$lib/pipeline-view/types';

export type PipelineModeFilter = 'all' | 'direct' | 'virtual';

export type DestructionController = {
	readonly open: boolean;
	readonly operation: DestructionOperation | null;
	readonly plan: DestructionPlan | null;
	readonly planning: boolean;
	readonly error: string | null;
	setOpen(open: boolean): void;
	start(operation: DestructionOperation, pipelineNames?: string[]): Promise<void>;
	addRequiredDependentsAndReplan(): Promise<void>;
};
