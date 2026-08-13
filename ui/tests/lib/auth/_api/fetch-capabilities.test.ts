import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchCapabilities } from '../../../../src/lib/auth/_api/fetch-capabilities';

describe('fetch capabilities', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given an authenticated user when fetching then capabilities are decoded', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				new Response(
					JSON.stringify({
						systemAdmin: false,
						project: 'analytics',
						target: 'prod',
						permissions: ['project.reload'],
						pipelinePermissions: { 'build.direct.run': ['ingestion'] },
						staleRoles: []
					})
				)
			)
		);

		await expect(fetchCapabilities()).resolves.toMatchObject({
			project: 'analytics',
			permissions: ['project.reload']
		});
	});

	it('given a missing capabilities endpoint when fetching then null is returned', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 404 })));

		await expect(fetchCapabilities()).resolves.toBeNull();
	});
});
