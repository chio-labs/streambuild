/**
 * The single data-access swap point — now backed by the `stb dev` API.
 *
 * The root layout gates rendering until the first definitions+state fetch has
 * landed, so pages keep the synchronous `getProject()` contract from the mock
 * era. The returned object is a deeply reactive $state proxy that polling
 * updates in place — derived values in mounted pages recompute without any
 * page-side subscription code.
 *
 * Note the tier: everything here is satisfiable by a READ-ONLY warehouse
 * connection plus connection-free compilation. `stb build` is deliberately not
 * represented. Audits and tests are (both are pure `client.query()` in
 * StreamBuild, so they're reads).
 */

import { app } from '$lib/api/store.svelte';
import { planFromServer } from '$lib/api/mapping';
import type { Deployment, DeploymentDetail, Plan, Project } from '$lib/domain/types';

export class ApiError extends Error {
	constructor(
		message: string,
		readonly status: number
	) {
		super(message);
		this.name = 'ApiError';
	}
}

/** Parse a successful JSON response or preserve useful text from any error body. */
export async function readApiResponse<T>(response: Response, operation: string): Promise<T> {
	if (!response.ok) throw await responseError(response, operation);
	try {
		return (await response.json()) as T;
	} catch {
		throw new ApiError(`${operation} returned an invalid JSON response`, response.status);
	}
}

async function responseError(response: Response, operation: string): Promise<ApiError> {
	let body = '';
	try {
		body = (await response.text()).trim();
	} catch {
		// A status-bearing fallback is still more useful than a body parsing error.
	}
	let detail: string | null = body || null;
	if (body) {
		try {
			const payload = JSON.parse(body) as { detail?: unknown };
			if (typeof payload.detail === 'string' && payload.detail.trim()) {
				detail = payload.detail.trim();
			}
		} catch {
			// Plain-text proxy and framework errors are already suitable messages.
		}
	}
	return new ApiError(detail ?? `${operation} failed (${response.status})`, response.status);
}

export function getProject(): Project {
	if (app.project === null) {
		throw new Error('getProject() called before the app finished loading');
	}
	return app.project;
}

/**
 * Whether this UI is allowed to mutate the warehouse. True since the execute
 * tier: the Plan page and lineage run panel POST /api/build, which runs the
 * exact `stb build` command shown, as a subprocess.
 */
export const CAN_EXECUTE_BUILD: boolean = true;

export type BuildStartResult = {
	invocationId: string;
	command: string;
	status: string;
};

/** Start one build; rejects with the server detail when one is already running. */
export async function startBuild(
	selectors: string[],
	startTime: string | null,
	confirmations: string[] = []
): Promise<BuildStartResult> {
	const response = await fetch('/api/build', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ selectors, startTime, confirmations })
	});
	return readApiResponse<BuildStartResult>(response, 'build start');
}

export type RunEvent = {
	sequence: number;
	emittedAt: string;
	event: string;
	stepId: string | null;
	phase: string | null;
	// run_started / statement / terminal payload fields, flattened server-side.
	command?: string;
	displayCommand?: string;
	selectors?: string[];
	startTime?: string | null;
	totalStatements?: number;
	selectedNodeCount?: number;
	statementSequence?: number;
	intent?: string;
	elapsedMs?: number;
	writtenRows?: number | null;
	errorMessage?: string | null;
	deferredUntil?: string | null;
	outcome?: string;
	exitCode?: number;
};

export type RunStatus =
	| 'succeeded'
	| 'failed'
	| 'cancelled'
	| 'running'
	| 'unresponsive'
	| 'presumed_failed';

export type RunEventFeed = {
	found: boolean;
	events: RunEvent[];
	hasMore: boolean;
	status: RunStatus | null;
	lastSignalAt: string | null;
	lastSignalAgeSeconds: number | null;
};

export type BuildFeed = {
	running: boolean;
	invocationId: string | null;
	command: string;
	exitCode: number | null;
	events: RunEvent[];
	stderr: string;
	forceAvailable: boolean;
};

/** Cursor read of the live build feed. */
export async function fetchBuildFeed(after: number): Promise<BuildFeed> {
	const response = await fetch(`/api/build/current?after=${after}`);
	return readApiResponse<BuildFeed>(response, 'build feed');
}

/** The durable step timeline of one recorded run. */
export async function fetchRunEvents(invocationId: string, after = 0): Promise<RunEventFeed> {
	const response = await fetch(
		`/api/runs/${encodeURIComponent(invocationId)}/events?after=${after}`
	);
	return readApiResponse<RunEventFeed>(response, 'run events');
}

export async function cancelBuild(invocationId: string): Promise<Record<string, unknown>> {
	return signalBuild('/api/build/cancel', invocationId);
}

export async function killBuild(invocationId: string): Promise<Record<string, unknown>> {
	return signalBuild('/api/build/kill', invocationId);
}

async function signalBuild(path: string, invocationId: string): Promise<Record<string, unknown>> {
	const response = await fetch(path, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ invocationId })
	});
	return readApiResponse<Record<string, unknown>>(response, 'build signal');
}

/** Fetch a server-side plan for the given selectors and optional start time. */
export async function fetchPlan(selectors: string[], startTime: string | null): Promise<Plan> {
	const params = new URLSearchParams();
	for (const selector of selectors) params.append('select', selector);
	if (startTime !== null) params.set('start', startTime);
	const response = await fetch(`/api/plan?${params}`);
	const payload = await readApiResponse<Record<string, unknown>>(response, 'plan request');
	return planFromServer(payload, getProject().adapter);
}

export type RunRecord = {
	invocationId: string;
	command: string;
	displayCommand: string | null;
	mode: string;
	status: RunStatus;
	outcome: RunStatus;
	exitCode: number | null;
	startedAt: string;
	completedAt: string | null;
	lastSignalAt: string;
	lastSignalAgeSeconds: number;
	durationMs: number;
	selectedNodeCount: number;
	errorMessage: string | null;
	toolVersion: string;
	lastActivity: string | null;
};

const RUNS_PREFETCH_MAX_AGE_MS = 10_000;
let runsPrefetch: Promise<RunRecord[]> | null = null;
let runsPrefetchedAt = 0;

/** Warm run history before navigation and share the recent result across routes. */
export function prefetchRuns(): Promise<RunRecord[]> {
	if (runsPrefetch !== null && Date.now() - runsPrefetchedAt < RUNS_PREFETCH_MAX_AGE_MS) {
		return runsPrefetch;
	}
	runsPrefetchedAt = Date.now();
	const request = requestRuns();
	runsPrefetch = request;
	void request.catch(() => {
		if (runsPrefetch === request) runsPrefetch = null;
	});
	return request;
}

/** Recorded invocation history from `_streambuild_invocations`, newest first. */
export async function fetchRuns(): Promise<RunRecord[]> {
	return prefetchRuns();
}

async function requestRuns(): Promise<RunRecord[]> {
	const response = await fetch('/api/runs');
	return readApiResponse<RunRecord[]>(response, 'runs request');
}

export type CheckStatusRecord = {
	kind: 'audit' | 'test';
	name: string;
	status:
		| 'passed'
		| 'warning'
		| 'failed'
		| 'error'
		| 'deferred'
		| 'binding_changed'
		| 'definition_changed'
		| 'execution_changed'
		| 'schedule_changed'
		| 'never_run';
	driftReasons: QualityDriftReason[];
	severity: string | null;
	failureCount: number;
	completedAt: string | null;
	payload: Record<string, unknown> | null;
	errorMessage: string | null;
};

export type QualityDriftReason =
	| 'binding_changed'
	| 'definition_changed'
	| 'execution_changed'
	| 'schedule_changed';

/** Last-known audit/test outcomes recorded in `_streambuild_node_results`. */
export async function fetchChecksStatus(): Promise<CheckStatusRecord[]> {
	const response = await fetch('/api/checks/status');
	return readApiResponse<CheckStatusRecord[]>(response, 'checks status request');
}

export type CheckRunResult = {
	passed: boolean;
	deferredUntil?: string | null;
	failingRowCount?: number;
	sampleColumns?: string[];
	sampleRows?: (string | number | null)[][];
	errorMessage?: string | null;
	targets?: {
		targetModelName: string;
		passed: boolean;
		columns?: string[];
		missingRows: (string | number | null)[][];
		unexpectedRows: (string | number | null)[][];
	}[];
};

/** Execute one audit or test read-only and return its outcome. */
export async function runCheck(kind: 'audit' | 'test', name: string): Promise<CheckRunResult> {
	const response = await fetch('/api/checks/run', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ kind, name })
	});
	return readApiResponse<CheckRunResult>(response, 'check run');
}

/** Every reconstructed deployment for the connected target database. */
export async function fetchDeployments(): Promise<Deployment[]> {
	const response = await fetch('/api/deployments');
	const payload = await readApiResponse<{ deployments: Deployment[] }>(response, 'deployments');
	return payload.deployments;
}

/** One deployment with its staged-versus-live model comparison. */
export async function fetchDeployment(deploymentId: string): Promise<DeploymentDetail> {
	const response = await fetch(`/api/deployments/${encodeURIComponent(deploymentId)}`);
	return readApiResponse<DeploymentDetail>(response, 'deployment');
}

export type DeploymentDiffRelation = {
	logicalName: string;
	status: 'added' | 'removed' | 'changed' | 'unchanged' | 'physical_missing';
	fromPhysicalName: string | null;
	toPhysicalName: string | null;
	fromRowCount: number | null;
	toRowCount: number | null;
	addedColumns: string[];
	removedColumns: string[];
};

export type DeploymentDiff = {
	database: string;
	fromEndpoint: string;
	toEndpoint: string;
	relations: DeploymentDiffRelation[];
};

/** Compare a deployment against the active bindings, or an explicit endpoint. */
export async function fetchDeploymentDiff(
	deploymentId: string,
	against: string | null = null
): Promise<DeploymentDiff> {
	const query = against === null ? '' : `?against=${encodeURIComponent(against)}`;
	const response = await fetch(
		`/api/deployments/${encodeURIComponent(deploymentId)}/diff${query}`
	);
	return readApiResponse<DeploymentDiff>(response, 'deployment diff');
}

export type PromoteResult = {
	invocationId: string;
	deploymentId: string;
	publishedViews: { logicalName: string; physicalName: string }[];
	graphAtomicPublish: boolean;
};

/** Promote one deployment; the server records it as a run the run page can read. */
export async function promoteDeployment(deploymentId: string): Promise<PromoteResult> {
	const response = await fetch(`/api/deployments/${encodeURIComponent(deploymentId)}/promote`, {
		method: 'POST'
	});
	return readApiResponse<PromoteResult>(response, 'deployment promote');
}

export type CleanupResult = {
	invocationId: string;
	removedRelations: number;
	removedDeployments: number;
};

/** Apply janitor cleanup for deployments outside the retention window. */
export async function cleanupDeployments(retentionDays: number): Promise<CleanupResult> {
	const response = await fetch('/api/deployments/cleanup', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ retentionDays })
	});
	return readApiResponse<CleanupResult>(response, 'deployment cleanup');
}
