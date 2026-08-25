import type { Model, ModelRef, Pipeline, Project, Source } from '$lib/domain/types';

type StreamTree = ReturnType<typeof import('$lib/domain/main/pipelines/stream-tree').streamTree>;
type AuditCounts = ReturnType<typeof import('$lib/domain/main/quality/audit-counts').auditCounts>;

export type PipelineSideReference = { readonly from: string; readonly ref: ModelRef };

export type PipelineViewSnapshot = {
	readonly pipeline: Pipeline | undefined;
	readonly source: Source | undefined;
	readonly tree: StreamTree;
	readonly models: Model[];
	readonly sideReferences: PipelineSideReference[];
};

export type PipelineViewFacade = {
	snapshot(project: Project, pipelineName: string): PipelineViewSnapshot;
	auditCounts(project: Project, modelName: string): AuditCounts;
	formatAgo(value: string | null, now: string): string;
	formatCompact(value: number): string;
	formatDuration(value: number): string;
	formatRate(value: number): string;
	formatTimestamp(value: string | null): string;
	refTypeLabel: Readonly<Record<ModelRef['type'], string>>;
};

export type DestructionOperation = 'destroy_pipelines' | 'reset_target';

export type DestructionResource = {
	name: string;
	kind: string;
	logicalName: string;
	pipelineName: string | null;
	exists: boolean;
	bytes: number | null;
	activeParts: number | null;
};

export type DestructionPlan = {
	planId: string;
	planFingerprint: string;
	operation: DestructionOperation;
	target: string;
	database: string;
	selectedPipelines: string[];
	includedDependentPipelines: string[];
	affectedPipelines: string[];
	requiredDependentPipelines: string[];
	blocked: boolean;
	models: string[];
	resources: DestructionResource[];
	managedSourcesIncluded: boolean;
	retainedReplayDataIncluded: boolean;
	estimatedBytes: number;
	dropSizeLimitBytes: number | null;
	dropSizeServerLimitBytes: number | null;
	dropSizeOverrideBytes: number | null;
	challengeValues: string[];
	expiresAt: string;
	reviewedAt: string | null;
};

export type ReviewedDestructionPlan = DestructionPlan & {
	reviewedAt: string;
};

export type DestructionExecution = {
	invocationId: string;
	status: string;
};
