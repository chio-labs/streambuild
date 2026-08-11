import type { BuildFeed, RunEvent, RunEventFeed, RunRecord, RunStatus } from '$lib/api/types';
import type { Project } from '$lib/domain/types';
import type { Graph } from '$lib/lineage/types';

export type RunDetailSnapshot = {
	feed: RunEventFeed;
	ownership: BuildFeed;
	record: RunRecord | null;
};

export type RunDetailSnapshotResource = {
	prefetch(invocationId: string): Promise<RunDetailSnapshot>;
	consume(invocationId: string): Promise<RunDetailSnapshot>;
	stop(): void;
};

export type RunDetailPollingResource = {
	schedule(delayMs: number): void;
	stop(): void;
};

export type RunDetailView = {
	events: RunEvent[];
	running: boolean;
	status: RunStatus;
	exitCode: number | null;
	stderr: string;
	owned: boolean;
	ownedRunning: boolean;
	ownerInvocationId: string | null;
	forceAvailable: boolean;
	signalling: boolean;
	lastSignalAgeSeconds: number | null;
	record: RunRecord | null;
	commandLine: string;
	loadError: string | null;
	pollError: string | null;
	notFound: boolean;
	initialLoading: boolean;
};

export type RunDetailController = {
	readonly view: RunDetailView;
	start(invocationId: string, live: boolean): void;
	stop(): void;
	requestCancel(): Promise<void>;
	requestKill(): Promise<void>;
};

export type RunPresentationInput = {
	project: Project;
	events: RunEvent[];
	running: boolean;
	status: RunStatus;
	commandLine: string;
	record: RunRecord | null;
	nowMs: number;
};

export type TimelineEvent = {
	sequence: number;
	event: string;
	stepId?: string | null;
	statementSequence?: number;
};

export type RunGraphInput = {
	project: Project;
	events: RunEvent[];
	running: boolean;
	outcome: RunStatus;
	startedEvent: RunEvent | undefined;
	record: RunRecord | null;
	commandLine: string;
};

export type RunNodeNote = {
	text: string;
	tone: 'info' | 'warn';
};

export type RunGraphPresentation = {
	runGraph: Graph;
	mutedIds: Set<string>;
	notes: Map<string, RunNodeNote>;
	recordedScopeCount: number;
	missingScopeCount: number;
};

export type RunPresentation = RunGraphPresentation & {
	startedEvent: RunEvent | undefined;
	completedStatements: RunEvent[];
	totalStatements: number | null;
	statementSummary: string | null;
	displayCommand: string;
	retryHref: string | null;
	outcome: RunStatus;
	outcomeColor: string;
	timeline: RunEvent[];
	eventLabels: Map<number, string>;
	durationSeconds: number | null;
};

export type RunEventLabelContext = {
	displayCommand: string;
	metadataPreparationCount: number;
	metadataMigrationCount: number;
	candidateMetadataCount: number;
	publicationCount: number;
	reconcileCount: number;
};

export type RunActivityPresentation = {
	startedEvent: RunEvent | undefined;
	completedStatements: RunEvent[];
	totalStatements: number | null;
	statementSummary: string | null;
	displayCommand: string;
	retryHref: string | null;
	durationSeconds: number | null;
};
