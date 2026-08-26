import { requestDeployments } from '$lib/api/_api/deployments';
import {
	requestProjectReload,
	requestWarehouseRefresh
} from '$lib/api/_api/project-actions';
import {
	requestDefinitionsPayload,
	requestStatePayload,
	requestStatusPayload
} from '$lib/api/_api/project';
import { requestCheckStatuses } from '$lib/api/_api/quality';
import { applyRecordedCheckStatuses, projectFromServer } from '$lib/api/_helpers/mapping';
import {
	createKafkaLagRetryResource,
	type KafkaLagRetryResource
} from '$lib/api/_resources/kafka-lag-retry.resource';
import {
	createPollingResource,
	type PollingResource
} from '$lib/api/_resources/polling.resource';
import {
	createVisibilityResource,
	type VisibilityResource
} from '$lib/api/_resources/visibility.resource';
import type { AppController, AppState, BootstrapPayload, CompileError } from '$lib/api/types';
import type { Project } from '$lib/domain/types';

export function createAppState(): AppController {
	const app: AppState = $state({
		phase: 'loading',
		status: null,
		project: null,
		deployments: [],
		reloading: false,
		fetchError: null
	});
	let liveStateRequestGeneration: number = 0;
	let liveStateRequest: Promise<void> | null = null;
	let liveStateController: AbortController | null = null;
	let definitionsPayload: Record<string, unknown> | null = null;
	let definitionsVersionKey: string | null = null;
	let deploymentsRequest: Promise<void> | null = null;
	const polling: PollingResource = createPollingResource(() => refreshLiveState());
	const visibility: VisibilityResource = createVisibilityResource(() => refreshLiveState());
	const kafkaLagRetry: KafkaLagRetryResource = createKafkaLagRetryResource(() =>
		refreshLiveState()
	);

	async function initialize(): Promise<void> {
		await refreshAll();
		polling.start();
		visibility.start();
	}

	function initializeFromBootstrap(payload: BootstrapPayload): void {
		applyStatusPayload(payload.status);
		if (app.status?.state !== 'ok' || payload.definitions === null) {
			app.phase = 'compile_failing';
		} else {
			definitionsPayload = payload.definitions;
			definitionsVersionKey = app.status.versionKey;
			mergeProject(payload.definitions, payload.state ?? {});
			app.phase = 'ready';
			app.fetchError = null;
			kafkaLagRetry.schedule(app.project);
			void Promise.all([refreshDeployments(), refreshRecordedChecks()]);
		}
		polling.start();
		visibility.start();
	}

	async function reload(): Promise<void> {
		liveStateRequestGeneration += 1;
		app.reloading = true;
		kafkaLagRetry.reset();
		try {
			applyStatusPayload(await requestProjectReload());
			if (app.status?.state === 'ok') await refreshDefinitionsAndState();
			else app.phase = app.project === null ? 'compile_failing' : 'ready';
		} catch (error) {
			app.phase = 'unreachable';
			app.fetchError = String(error);
		} finally {
			app.reloading = false;
		}
	}

	// Polling reads the server's held snapshot. Only an explicit refresh requests
	// connection recovery and discards it, so routine polls never pay for a rebuild.
	async function refreshLiveState(options?: { force?: boolean }): Promise<void> {
		if (app.project === null) return;
		if (liveStateRequest !== null && options?.force !== true) return liveStateRequest;
		if (options?.force === true) liveStateController?.abort();
		const requestGeneration: number = ++liveStateRequestGeneration;
		liveStateController = new AbortController();
		const request: Promise<void> = refreshLiveStateRequest(
			requestGeneration,
			liveStateController.signal,
			options?.force === true
		);
		const trackedRequest: Promise<void> = request.finally(() => {
			if (liveStateRequest === trackedRequest) liveStateRequest = null;
		});
		liveStateRequest = trackedRequest;
		return liveStateRequest;
	}

	async function refreshLiveStateRequest(
		requestGeneration: number,
		signal: AbortSignal,
		force: boolean
	): Promise<void> {
		try {
			if (force) applyStatusPayload(await requestWarehouseRefresh(signal));
			else applyStatusPayload(await requestStatusPayload(signal));
			const versionKey: string = app.status?.versionKey ?? '';
			if (app.status?.state !== 'ok') {
				app.phase = app.project === null ? 'compile_failing' : 'ready';
				return;
			}
			if (!app.status?.warehouseConnected) {
				const definitions: Record<string, unknown> = await loadDefinitions(versionKey, signal);
				if (requestGeneration !== liveStateRequestGeneration) return;
				mergeProject(definitions, {});
				app.phase = 'ready';
				return;
			}
			const state: Record<string, unknown> | null = await requestStatePayload(signal);
			if (requestGeneration !== liveStateRequestGeneration) return;
			if (state === null) return;
			const definitions: Record<string, unknown> = await loadDefinitions(versionKey, signal);
			if (requestGeneration !== liveStateRequestGeneration) return;
			mergeProject(definitions, state);
			if (force) void refreshRecordedChecks();
			else await refreshRecordedChecks();
			kafkaLagRetry.schedule(app.project);
		} catch (error) {
			if (error instanceof Error && error.name === 'AbortError') return;
			return;
		}
	}

	async function loadDefinitions(
		versionKey: string,
		signal?: AbortSignal
	): Promise<Record<string, unknown>> {
		if (definitionsPayload !== null && definitionsVersionKey === versionKey) {
			return definitionsPayload;
		}
		const definitions: Record<string, unknown> = await requestDefinitionsPayload(
			versionKey,
			signal
		);
		definitionsPayload = definitions;
		definitionsVersionKey = versionKey;
		return definitions;
	}

	async function refreshDeployments(): Promise<void> {
		if (deploymentsRequest !== null) return deploymentsRequest;
		deploymentsRequest = requestDeployments()
			.then((deployments) => {
				app.deployments = deployments;
			})
			.catch(() => undefined)
			.finally(() => {
				deploymentsRequest = null;
			});
		return deploymentsRequest;
	}

	async function refreshRecordedChecks(): Promise<void> {
		if (app.project === null) return;
		try {
			applyRecordedCheckStatuses(app.project, await requestCheckStatuses());
		} catch {
			return;
		}
	}

	async function refreshAll(): Promise<void> {
		try {
			applyStatusPayload(await requestStatusPayload());
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
			const versionKey: string = app.status?.versionKey ?? '';
			if (!app.status?.warehouseConnected) {
				mergeProject(await loadDefinitions(versionKey), {});
				app.phase = 'ready';
				app.fetchError = null;
				return;
			}
			const [definitions, state]: [Record<string, unknown>, Record<string, unknown> | null] =
				await Promise.all([
					loadDefinitions(versionKey),
					requestStatePayload()
				]);
			mergeProject(definitions, state ?? {});
			app.phase = 'ready';
			app.fetchError = null;
			kafkaLagRetry.schedule(app.project);
			void Promise.all([refreshDeployments(), refreshRecordedChecks()]);
		} catch (error) {
			app.phase = 'unreachable';
			app.fetchError = String(error);
		}
	}

	function mergeProject(
		definitions: Record<string, unknown>,
		state: Record<string, unknown>
	): void {
		const next: Project = projectFromServer(definitions, state);
		if (app.project === null) {
			app.project = next;
			return;
		}
		for (const audit of next.audits) {
			const previous: Project['audits'][number] | undefined = app.project.audits.find(
				(item) => item.name === audit.name
			);
			if (previous?.result) audit.result = previous.result;
		}
		for (const test of next.tests) {
			const previous: Project['tests'][number] | undefined = app.project.tests.find(
				(item) => item.name === test.name
			);
			if (previous?.result) test.result = previous.result;
		}
		Object.assign(app.project, next);
	}

	function applyStatusPayload(payload: Record<string, unknown>): void {
		const compile: Record<string, unknown> = (payload.compile ?? {}) as Record<string, unknown>;
		const warehouse: Record<string, unknown> = (payload.warehouse ?? {}) as Record<string, unknown>;
		app.status = {
			state: compile.state === 'ok' ? 'ok' : 'failing',
			toolVersion: String(payload.toolVersion ?? ''),
			versionKey: String(compile.versionKey ?? ''),
			compiledAt: String(compile.compiledAt ?? ''),
			timings: (compile.timings as Record<string, number> | null) ?? null,
			error: (compile.error as CompileError | null) ?? null,
			warehouseConnected: Boolean(warehouse.connected ?? false),
			warehouseError: (warehouse.error as string | null) ?? null,
			warehouseState: String(warehouse.state ?? 'retrying'),
			warehouseLastAttemptAt: (warehouse.lastAttemptAt as string | null) ?? null,
			warehouseNextAttemptAt: (warehouse.nextAttemptAt as string | null) ?? null
		};
	}

	return {
		app,
		initialize,
		initializeFromBootstrap,
		reload,
		refreshLiveState,
		refreshDeployments
	};
}
