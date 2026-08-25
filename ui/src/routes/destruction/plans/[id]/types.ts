import type {
	DestructionExecution,
	DestructionPlan,
	DestructionResource
} from '$lib/pipeline-view/types';

export type ResourcePageSize = 25 | 50 | 100;

export type DestructionModelListState = {
	readonly expanded: boolean;
	readonly visible: readonly string[];
	toggle(): void;
};

export type DestructionResourceListState = {
	readonly page: number;
	readonly pageSize: ResourcePageSize;
	readonly pageCount: number;
	readonly first: number;
	readonly last: number;
	readonly visible: readonly DestructionResource[];
	readonly existingCount: number;
	readonly absentCount: number;
	setPage(page: number): void;
	setPageSize(size: ResourcePageSize): void;
};

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
	readonly modelList: DestructionModelListState;
	readonly resourceList: DestructionResourceListState;
	load(planId: string): Promise<void>;
	cancel(): void;
	review(): Promise<void>;
	setResponse(index: number, value: string): void;
	execute(): Promise<DestructionExecution | null>;
};
