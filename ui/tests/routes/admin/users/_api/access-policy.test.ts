import { describe, expect, it, vi } from 'vitest';

const authenticatedFetch = vi.hoisted(() => vi.fn());
vi.mock('$lib/auth/main/authenticated-fetch', () => ({ authenticatedFetch }));

import { fetchAccessPolicy } from '../../../../../src/routes/admin/users/_api/access-policy';

describe('access policy API', () => {
	it('given a compiled policy when fetching then roles and grants are decoded', async () => {
		authenticatedFetch.mockResolvedValue(
			new Response(
				JSON.stringify({
					present: true,
					fingerprint: 'abc',
					roles: [
						{
							name: 'operator',
							description: 'Operate ingestion',
							grants: [
								{ scope: null, pipelines: ['ingestion'], permissions: ['build.direct.run'] },
								{ scope: 'project', pipelines: [], permissions: ['project.reload'] }
							]
						}
					]
				})
			)
		);

		await expect(fetchAccessPolicy()).resolves.toMatchObject({
			present: true,
			roles: [{ name: 'operator' }]
		});
		expect(authenticatedFetch).toHaveBeenCalledWith('/api/access-policy');
	});
});
