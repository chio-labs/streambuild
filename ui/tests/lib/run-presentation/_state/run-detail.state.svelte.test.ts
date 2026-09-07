import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { BuildFeed, RunEventFeed } from '$lib/api/types';
import type { RunDetailController, RunDetailSnapshot } from '$lib/run-presentation/types';

type RunDetailMocks = {
	consumeRunDetail: ReturnType<typeof vi.fn>;
	schedule: ReturnType<typeof vi.fn>;
	stop: ReturnType<typeof vi.fn>;
};

const mocks: RunDetailMocks = vi.hoisted((): RunDetailMocks => ({
	consumeRunDetail: vi.fn(),
	schedule: vi.fn(),
	stop: vi.fn()
}));

vi.mock('$lib/run-presentation/main/_consume-run-detail', () => ({
	consumeRunDetail: mocks.consumeRunDetail
}));
vi.mock('$lib/run-presentation/_resources/run-detail-polling.resource', () => ({
	createRunDetailPollingResource: vi.fn(() => ({ schedule: mocks.schedule, stop: mocks.stop }))
}));

import { createRunDetailState } from '$lib/run-presentation/_state/run-detail.state.svelte';

const FEED: RunEventFeed = {
	found: true,
	events: [
		{
			sequence: 1,
			emittedAt: '2026-08-11 00:00:00',
			event: 'run_started',
			stepId: null,
			phase: null,
			displayCommand: 'stb build orders'
		}
	],
	hasMore: false,
	status: 'running',
	lastSignalAt: '2026-08-11 00:00:00',
	lastSignalAgeSeconds: 0,
	statementProgress: {
		found: true,
		queryId: 'query-1',
		statementSequence: 1,
		stepId: 'replay_orders',
		phase: 'replay',
		observedAt: '2026-08-11 00:00:00',
		elapsedSeconds: 5
	}
};

const OWNERSHIP: BuildFeed = {
	running: true,
	invocationId: 'run-1',
	currentInvocationId: 'run-1',
	command: 'stb build orders',
	exitCode: null,
	events: [],
	stderr: '',
	forceAvailable: false
};

describe('run detail state', () => {
	beforeEach(() => vi.clearAllMocks());

	it('given an initial active snapshot when started then the view is populated and polling continues', async () => {
		const snapshot: RunDetailSnapshot = { feed: FEED, ownership: OWNERSHIP, record: null };
		mocks.consumeRunDetail.mockResolvedValueOnce(snapshot);
		const navigate: ReturnType<typeof vi.fn<(invocationId: string) => Promise<void>>> = vi.fn<
			(invocationId: string) => Promise<void>
		>(() => Promise.resolve());
		const controller: RunDetailController = createRunDetailState(navigate);

		controller.start('run-1', true);
		await vi.waitFor((): void => expect(controller.view.initialLoading).toBe(false));

		expect(controller.view.commandLine).toBe('stb build orders');
		expect(controller.view.events).toEqual(FEED.events);
		expect(controller.view.statementProgress).toEqual(FEED.statementProgress);
		expect(mocks.schedule).toHaveBeenCalledWith(1_200);
	});

	it('given a just-launched live run without evidence when started then it polls through the launch grace period', async () => {
		const snapshot: RunDetailSnapshot = {
			feed: {
				found: false,
				events: [],
				hasMore: false,
				status: null,
				lastSignalAt: null,
				lastSignalAgeSeconds: null,
				statementProgress: null
			},
			ownership: { ...OWNERSHIP, running: false, invocationId: null, currentInvocationId: null },
			record: null
		};
		mocks.consumeRunDetail.mockResolvedValueOnce(snapshot);
		const controller: RunDetailController = createRunDetailState(() => Promise.resolve());

		controller.start('destruction-run-1', true);
		await vi.waitFor((): void => expect(mocks.schedule).toHaveBeenCalledWith(1_200));

		expect(controller.view.initialLoading).toBe(true);
		expect(controller.view.notFound).toBe(false);
	});

	it('given owned warehouse cancellation failure when polling then the view keeps it visible and actionable', async () => {
		const snapshot: RunDetailSnapshot = {
			feed: FEED,
			ownership: {
				...OWNERSHIP,
				cancellationStatus: 'cancellation_failed',
				cancellationError: 'ClickHouse query remained active',
				forceAvailable: true
			},
			record: null
		};
		mocks.consumeRunDetail.mockResolvedValueOnce(snapshot);
		const controller: RunDetailController = createRunDetailState(() => Promise.resolve());

		controller.start('run-1', true);
		await vi.waitFor((): void => expect(controller.view.initialLoading).toBe(false));

		expect(controller.view.status).toBe('cancellation_failed');
		expect(controller.view.running).toBe(true);
		expect(controller.view.forceAvailable).toBe(true);
		expect(controller.view.cancellationError).toBe('ClickHouse query remained active');
	});

	it('given a durable cancellation failure for an unowned run when polling then stale local ownership does not override it', async () => {
		mocks.consumeRunDetail.mockResolvedValueOnce({
			feed: { ...FEED, status: 'cancellation_failed' },
			ownership: {
				...OWNERSHIP,
				invocationId: 'another-run',
				currentInvocationId: 'another-run',
				cancellationStatus: 'cancelling'
			},
			record: null
		});
		const controller: RunDetailController = createRunDetailState(() => Promise.resolve());

		controller.start('run-1', false);
		await vi.waitFor((): void => expect(controller.view.initialLoading).toBe(false));

		expect(controller.view.status).toBe('cancellation_failed');
		expect(controller.view.running).toBe(false);
		expect(controller.view.owned).toBe(false);
	});
});
