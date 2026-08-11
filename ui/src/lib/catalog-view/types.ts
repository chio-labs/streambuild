import type { SqlArtifact } from '$lib/presentation/components/sql-block.svelte';
import type {
	Audit,
	Model,
	Project,
	ReconstructionCoverage,
	RefType,
	Source,
	SqlTest
} from '$lib/domain/types';

export type CatalogModelView = {
	readonly model: Model | undefined;
	readonly audits: Audit[];
	readonly tests: SqlTest[];
	readonly source: Source | undefined;
	readonly coverage: ReconstructionCoverage | undefined;
	readonly artifacts: SqlArtifact[];
	readonly upstream: Model['refs'];
	readonly downstream: Model[];
};

export type CatalogViewFacade = {
	modelView(project: Project, modelName: string): CatalogModelView;
	formatAgo(value: string | null, now: string): string;
	formatBytes(value: number): string;
	formatDaySpan(value: number): string;
	formatDuration(value: number): string;
	formatInteger(value: number): string;
	formatTimestamp(value: string | null): string;
	ownershipLabel: Readonly<Record<string, string>>;
	refTypeLabel: Readonly<Record<RefType, string>>;
};
