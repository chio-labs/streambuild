import { describe, expect, it, vi } from 'vitest';

const authenticatedFetch = vi.hoisted(() => vi.fn());
vi.mock('$lib/auth/main/authenticated-fetch', () => ({ authenticatedFetch }));

import {
	grantProjectRole,
	listProjectRoles,
	revokeProjectRole
} from '../../../../../src/routes/admin/users/_api/user-project-role';
import type { ProjectRoleAssignment } from '../../../../../src/routes/admin/users/types';

const assignment: ProjectRoleAssignment = {
	assignmentId: '2f6d3f0e-8f6a-4b56-9f0f-52f16f7a2b31',
	userId: 'd0b46a1e-7553-47bd-9188-fcf59fbed050',
	projectName: 'analytics',
	role: 'operator',
	targetName: 'prod',
	assignedBy: null,
	assignedAt: '2026-01-01T00:00:00Z',
	revokedBy: null,
	revokedAt: null
};

describe('project role API', () => {
	it('given an assignment when granting then the decoded assignment is returned', async () => {
		authenticatedFetch.mockResolvedValue(new Response(JSON.stringify(assignment)));

		await expect(
			grantProjectRole(assignment.userId, 'analytics', 'operator', 'prod')
		).resolves.toMatchObject({ role: 'operator', targetName: 'prod' });
		expect(authenticatedFetch).toHaveBeenCalledWith(
			`/api/admin/users/${assignment.userId}/project-roles`,
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ projectName: 'analytics', role: 'operator', targetName: 'prod' })
			})
		);
	});

	it('given a project when listing then decoded assignments are returned', async () => {
		authenticatedFetch.mockResolvedValue(new Response(JSON.stringify([assignment])));

		await expect(listProjectRoles(assignment.userId, 'analytics')).resolves.toHaveLength(1);
	});

	it('given an assignment when revoking then the revocation payload is returned', async () => {
		authenticatedFetch.mockResolvedValue(
			new Response(JSON.stringify({ ...assignment, revokedAt: '2026-01-02T00:00:00Z' }))
		);

		await expect(revokeProjectRole(assignment.assignmentId)).resolves.toMatchObject({
			revokedAt: '2026-01-02T00:00:00Z'
		});
	});
});
