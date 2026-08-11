import type { RunRecord } from '$lib/api/types';
import type { Project, Source } from '$lib/domain/types';
import type { Plan, PlanSqlChangeStatus, ReplayWindow, Selector } from '$lib/planning/types';

export type ParsedPlanLocation = {
	readonly selectors: Selector[];
	readonly replayWindow: ReplayWindow;
	readonly deploymentId: string | null;
};

export type ParsedPlanCommand = {
	readonly selectors: Selector[];
	readonly replayWindow: ReplayWindow;
	readonly deploymentId: string | null;
};

export type PlanViewTypes = {
	project: Project;
	source: Source;
	plan: Plan;
	runRecord: RunRecord;
	selector: Selector;
	replayWindow: ReplayWindow;
};

export type PlanViewFacade = {
	readLocation(url: URL): ParsedPlanLocation;
	locationRequestKey(url: URL): string;
	shouldClearReplayStart(url: URL): boolean;
	selectionUrl(
		url: URL,
		selectors: Selector[],
		replayWindow?: ReplayWindow,
		deploymentId?: string | null
	): URL;
	deploymentUrl(url: URL, deploymentId: string): URL;
	replayStartToken(replayWindow: ReplayWindow): string | null;
	parseCommand(command: string): ParsedPlanCommand;
	boundaryColumns(root: Plan['replayRoots'][number]): string | null;
	rootSources(project: Project, modelNames: string[]): Source[];
	selectorToken(selector: Selector): string;
	formatAgo(value: string | null, now: string): string;
	formatClock(value: string): string;
	formatCompact(value: number): string;
	formatDuration(value: number): string;
	sqlChangeLabel: Readonly<Record<PlanSqlChangeStatus, string>>;
	sqlChangeColour: Readonly<Record<PlanSqlChangeStatus, string>>;
	ownershipLabel: Readonly<Record<string, string>>;
};
