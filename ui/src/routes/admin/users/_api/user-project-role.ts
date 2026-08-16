import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';
import { projectRoleAssignmentSchema, projectRoleAssignmentsSchema } from '../schemas';
import type { ProjectRoleAssignment } from '../types';
import { readUsersResponse } from './read-users-response';

export async function listProjectRoles(
	userId: string,
	projectName: string
): Promise<ProjectRoleAssignment[]> {
	const response: Response = await authenticatedFetch(
		`/api/admin/users/${encodeURIComponent(userId)}/project-roles?project=${encodeURIComponent(projectName)}`
	);
	return readUsersResponse(response, projectRoleAssignmentsSchema, 'List project roles');
}

export async function grantProjectRole(
	userId: string,
	projectName: string,
	role: string,
	targetName: string | null
): Promise<ProjectRoleAssignment> {
	const response: Response = await authenticatedFetch(
		`/api/admin/users/${encodeURIComponent(userId)}/project-roles`,
		{
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ projectName, role, targetName })
		}
	);
	return readUsersResponse(response, projectRoleAssignmentSchema, 'Grant project role');
}

export async function revokeProjectRole(assignmentId: string): Promise<ProjectRoleAssignment> {
	const response: Response = await authenticatedFetch(
		`/api/admin/project-roles/${encodeURIComponent(assignmentId)}`,
		{ method: 'DELETE' }
	);
	return readUsersResponse(response, projectRoleAssignmentSchema, 'Revoke project role');
}
