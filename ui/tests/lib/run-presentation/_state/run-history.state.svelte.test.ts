import { describe, expect, it, vi } from 'vitest';

import type { RunRecord } from '$lib/api/types';

const requests: { fetchRuns: ReturnType<typeof vi.fn> } = vi.hoisted(() => ({
	fetchRuns: vi.fn()
}));

vi.mock('$lib/api/main/runs/fetch-runs', () => ({ fetchRuns: requests.fetchRuns }));

import { createRunHistoryState } from '$lib/run-presentation/main/create-run-history-state.svelte';
import type { RunHistoryState } from '$lib/run-presentation/types';

describe('run history state', () => {
	it('given concurrent refreshes when history loads then one request updates retained data', async () => {
		const records: RunRecord[] = [];
		requests.fetchRuns.mockResolvedValueOnce(records);
		const state: RunHistoryState = createRunHistoryState();
		const stop: () => void = state.start();

		await Promise.all([state.refresh(), state.refresh()]);
		await vi.waitFor(() => expect(state.runs).toEqual(records));

		expect(requests.fetchRuns).toHaveBeenCalledOnce();
		expect(state.updatedAt).not.toBeNull();
		stop();
	});
});
