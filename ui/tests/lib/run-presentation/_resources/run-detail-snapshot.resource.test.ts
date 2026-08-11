import { afterEach, describe, expect, it, vi } from 'vitest';

import type { BuildFeed } from '$lib/api/types';
import { createRunDetailSnapshotResource } from '$lib/run-presentation/_resources/run-detail-snapshot.resource';
import type {
	RunDetailSnapshot,
	RunDetailSnapshotResource
} from '$lib/run-presentation/types';

type ApiMocks = {
	fetchBuildFeed: ReturnType<typeof vi.fn>;
	fetchRunEvents: ReturnType<typeof vi.fn>;
	fetchRuns: ReturnType<typeof vi.fn>;
};

const api: ApiMocks = vi.hoisted((): ApiMocks => ({
	fetchBuildFeed: vi.fn(),
	fetchRunEvents: vi.fn(),
	fetchRuns: vi.fn()
}));

vi.mock('$lib/api/main/build/fetch-build-feed', () => ({ fetchBuildFeed: api.fetchBuildFeed }));
vi.mock('$lib/api/main/build/fetch-run-events', () => ({ fetchRunEvents: api.fetchRunEvents }));
vi.mock('$lib/api/main/runs/fetch-runs', () => ({ fetchRuns: api.fetchRuns }));

const OWNERSHIP: BuildFeed = {
	running: true,
	invocationId: 'run-1',
	currentInvocationId: 'run-1',
	command: 'build',
	exitCode: null,
	events: [],
	stderr: '',
	forceAvailable: false
};

describe('run detail snapshot resource', () => {
	afterEach((): void => {
		vi.clearAllMocks();
		vi.useRealTimers();
	});

	it('given an owned active run when prefetched twice then one shared snapshot is returned', async () => {
		vi.useFakeTimers();
		api.fetchBuildFeed.mockResolvedValue(OWNERSHIP);
		const resource: RunDetailSnapshotResource = createRunDetailSnapshotResource();

		const first: Promise<RunDetailSnapshot> = resource.prefetch('run-1');
		const second: Promise<RunDetailSnapshot> = resource.prefetch('run-1');
		const snapshot: RunDetailSnapshot = await first;
		resource.stop();

		expect(second).toBe(first);
		expect(snapshot.ownership).toBe(OWNERSHIP);
		expect(api.fetchBuildFeed).toHaveBeenCalledTimes(1);
		expect(api.fetchRunEvents).not.toHaveBeenCalled();
	});
});
