/**
 * The app's single server-state container.
 *
 * The root layout gates rendering on `phase`, so every page can keep calling
 * the synchronous `getProject()` and receive the same deeply-reactive object.
 * Polling REPLACES the object's top-level collections in place rather than
 * swapping the object, which is what keeps references held by mounted pages
 * live across refreshes.
 */

import { projectFromServer } from '$lib/api/mapping';
import type { Project } from '$lib/domain/types';

export type CompileError = {
	message: string;
	path: string | null;
	line: number | null;
	column: number | null;
};

export type ServerStatus = {
	state: 'ok' | 'failing';
	versionKey: string;
	compiledAt: string;
	timings: Record<string, number> | null;
	error: CompileError | null;
	warehouseConnected: boolean;
	warehouseError: string | null;
};

export type AppPhase = 'loading' | 'ready' | 'compile_failing' | 'unreachable';

const POLL_INTERVAL_MS = 30_000;

type AppState = {
	phase: AppPhase;
	status: ServerStatus | null;
	project: Project | null;
	reloading: boolean;
	fetchError: string | null;
};

export const app = $state<AppState>({
	phase: 'loading',
	status: null,
	project: null,
	reloading: false,
	fetchError: null
});

let pollTimer: ReturnType<typeof setInterval> | null = null;
let startedPolling = false;

export async function initializeApp(): Promise<void> {
	await refreshAll();
	startPolling();
}

export async function reloadProject(): Promise<void> {
	app.reloading = true;
	try {
		const response = await fetch('/api/reload', { method: 'POST' });
		applyStatusPayload(await response.json());
		if (app.status?.state === 'ok') {
			await refreshDefinitionsAndState();
		} else {
			app.phase = 'compile_failing';
		}
	} catch (error) {
		app.phase = 'unreachable';
		app.fetchError = String(error);
	} finally {
		app.reloading = false;
	}
}

export async function refreshLiveState(): Promise<void> {
	if (app.project === null) return;
	try {
		const [statusResponse, stateResponse] = await Promise.all([
			fetch('/api/status'),
			fetch('/api/state')
		]);
		applyStatusPayload(await statusResponse.json());
		if (app.status?.state !== 'ok') {
			app.phase = 'compile_failing';
			return;
		}
		if (!stateResponse.ok) return;
		const definitionsResponse = await fetch('/api/definitions');
		mergeProject(await definitionsResponse.json(), await stateResponse.json());
	} catch {
		// A missed poll is not an outage; the topbar keeps the last capturedAt.
	}
}

async function refreshAll(): Promise<void> {
	try {
		const statusResponse = await fetch('/api/status');
		applyStatusPayload(await statusResponse.json());
	} catch (error) {
		app.phase = 'unreachable';
		app.fetchError = String(error);
		return;
	}
	if (app.status?.state !== 'ok') {
		app.phase = 'compile_failing';
		return;
	}
	await refreshDefinitionsAndState();
}

async function refreshDefinitionsAndState(): Promise<void> {
	try {
		const [definitionsResponse, stateResponse] = await Promise.all([
			fetch('/api/definitions'),
			fetch('/api/state')
		]);
		const definitions = await definitionsResponse.json();
		const state = stateResponse.ok ? await stateResponse.json() : {};
		mergeProject(definitions, state);
		app.phase = 'ready';
		app.fetchError = null;
	} catch (error) {
		app.phase = 'unreachable';
		app.fetchError = String(error);
	}
}

function mergeProject(definitions: Record<string, unknown>, state: Record<string, unknown>): void {
	const next = projectFromServer(definitions, state);
	if (app.project === null) {
		app.project = next;
		return;
	}
	Object.assign(app.project, next);
}

function applyStatusPayload(payload: Record<string, unknown>): void {
	const compile = (payload.compile ?? {}) as Record<string, unknown>;
	const warehouse = (payload.warehouse ?? {}) as Record<string, unknown>;
	app.status = {
		state: compile.state === 'ok' ? 'ok' : 'failing',
		versionKey: String(compile.versionKey ?? ''),
		compiledAt: String(compile.compiledAt ?? ''),
		timings: (compile.timings as Record<string, number> | null) ?? null,
		error: (compile.error as CompileError | null) ?? null,
		warehouseConnected: Boolean(warehouse.connected ?? false),
		warehouseError: (warehouse.error as string | null) ?? null
	};
}

function startPolling(): void {
	if (startedPolling || typeof document === 'undefined') return;
	startedPolling = true;
	pollTimer = setInterval(() => {
		if (!document.hidden) void refreshLiveState();
	}, POLL_INTERVAL_MS);
	document.addEventListener('visibilitychange', () => {
		if (!document.hidden) void refreshLiveState();
	});
	void pollTimer;
}
