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
 * Whether this UI is allowed to mutate the warehouse. False in tier 1: the Plan
 * page previews and hands off a command instead of executing it.
 */
export const CAN_EXECUTE_BUILD: boolean = false;

/** Freshness of the warehouse read, shown in the topbar. */
export function getSyncState(): { connected: boolean; syncedAt: string } {
	return {
		connected: app.status?.warehouseConnected ?? false,
		syncedAt: app.project?.capturedAt ?? ''
	};
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

export type CheckRunResult = {
	passed: boolean;
	failingRowCount?: number;
	sampleColumns?: string[];
	sampleRows?: (string | number | null)[][];
	errorMessage?: string | null;
	targets?: {
		targetModelName: string;
		passed: boolean;
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
