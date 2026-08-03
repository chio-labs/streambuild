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
import type { Plan, Project } from '$lib/domain/types';

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
	startTime: string | null
): Promise<BuildStartResult> {
	const response = await fetch('/api/build', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ selectors, startTime })
	});
	if (!response.ok) {
		const detail = ((await response.json()) as { detail?: string }).detail;
		throw new Error(detail ?? `build start failed (${response.status})`);
	}
	return (await response.json()) as BuildStartResult;
}

export type RunEvent = {
	sequence: number;
	emittedAt: string;
	event: string;
	stepId: string | null;
	phase: string | null;
	// run_started / statement / terminal payload fields, flattened server-side.
	command?: string;
	totalStatements?: number;
	selectedNodeCount?: number;
	statementSequence?: number;
	intent?: string;
	elapsedMs?: number;
	writtenRows?: number | null;
	errorMessage?: string | null;
	outcome?: string;
	exitCode?: number;
};

export type BuildFeed = {
	running: boolean;
	invocationId: string | null;
	command: string;
	exitCode: number | null;
	events: RunEvent[];
	stderr: string;
};

/** Cursor read of the live build feed. */
export async function fetchBuildFeed(after: number): Promise<BuildFeed> {
	const response = await fetch(`/api/build/current?after=${after}`);
	if (!response.ok) throw new Error(`build feed failed (${response.status})`);
	return (await response.json()) as BuildFeed;
}

/** The durable step timeline of one recorded run. */
export async function fetchRunEvents(invocationId: string): Promise<RunEvent[]> {
	const response = await fetch(`/api/runs/${encodeURIComponent(invocationId)}/events`);
	if (!response.ok) throw new Error(`run events failed (${response.status})`);
	return (await response.json()) as RunEvent[];
}

/** Fetch a server-side plan for the given selectors and optional start time. */
export async function fetchPlan(selectors: string[], startTime: string | null): Promise<Plan> {
	const params = new URLSearchParams();
	for (const selector of selectors) params.append('select', selector);
	if (startTime !== null) params.set('start', startTime);
	const response = await fetch(`/api/plan?${params}`);
	if (!response.ok) {
		const detail = ((await response.json()) as { detail?: string }).detail;
		throw new Error(detail ?? `plan request failed (${response.status})`);
	}
	return planFromServer(await response.json(), getProject().adapter);
}

export type RunRecord = {
	invocationId: string;
	command: string;
	mode: string;
	outcome: string;
	exitCode: number;
	startedAt: string;
	completedAt: string;
	durationMs: number;
	selectedNodeCount: number;
	errorMessage: string | null;
	toolVersion: string;
};

/** Recorded invocation history from `_streambuild_invocations`, newest first. */
export async function fetchRuns(): Promise<RunRecord[]> {
	const response = await fetch('/api/runs');
	if (!response.ok) {
		const detail = ((await response.json()) as { detail?: string }).detail;
		throw new Error(detail ?? `runs request failed (${response.status})`);
	}
	return (await response.json()) as RunRecord[];
}

export type CheckStatusRecord = {
	kind: 'audit' | 'test';
	name: string;
	status: 'passed' | 'warning' | 'failed' | 'error' | 'stale' | 'never_run';
	severity: string | null;
	failureCount: number;
	completedAt: string | null;
	payload: Record<string, unknown> | null;
	errorMessage: string | null;
};

/** Last-known audit/test outcomes recorded in `_streambuild_node_results`. */
export async function fetchChecksStatus(): Promise<CheckStatusRecord[]> {
	const response = await fetch('/api/checks/status');
	if (!response.ok) {
		const detail = ((await response.json()) as { detail?: string }).detail;
		throw new Error(detail ?? `checks status request failed (${response.status})`);
	}
	return (await response.json()) as CheckStatusRecord[];
}

export type CheckRunResult = {
	passed: boolean;
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
	if (!response.ok) {
		const detail = ((await response.json()) as { detail?: string }).detail;
		throw new Error(detail ?? `check run failed (${response.status})`);
	}
	return (await response.json()) as CheckRunResult;
}
