import type {
	DestructionOperation,
	DestructionPlan,
	InactivePipeline
} from '$lib/pipeline-view/types';

export type PipelineModeFilter = 'all' | 'direct' | 'virtual';

export type DestructionController = {
	readonly open: boolean;
	readonly operation: DestructionOperation | null;
	readonly plan: DestructionPlan | null;
	readonly planning: boolean;
	readonly error: string | null;
	readonly inactivePipelines: InactivePipeline[];
	readonly loadingInactivePipelines: boolean;
	readonly inactivePipelinesError: string | null;
	setOpen(open: boolean): void;
	start(operation: DestructionOperation, pipelineNames?: string[]): Promise<void>;
	addRequiredDependentsAndReplan(): Promise<void>;
	loadInactivePipelines(): Promise<void>;
};
