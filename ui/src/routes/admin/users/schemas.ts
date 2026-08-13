import { z } from 'zod';

export const adminUserSchema = z.object({
	id: z.uuid(),
	username: z.string(),
	displayName: z.string().nullable(),
	email: z.string().nullable(),
	active: z.boolean(),
	roles: z.array(z.string()),
	authenticationSources: z.array(z.enum(['password', 'trusted_proxy'])),
	createdAt: z.string(),
	updatedAt: z.string()
});

export const adminUsersSchema = z.array(adminUserSchema);
export const usersErrorPayloadSchema = z.object({ detail: z.string().optional() });
export const usersOkStatusSchema = z.object({ status: z.literal('ok') });

export const projectRoleAssignmentSchema = z.object({
	assignmentId: z.uuid(),
	userId: z.uuid(),
	projectName: z.string(),
	role: z.string(),
	targetName: z.string().nullable(),
	assignedBy: z.string().nullable(),
	assignedAt: z.string(),
	revokedBy: z.string().nullable(),
	revokedAt: z.string().nullable()
});

export const projectRoleAssignmentsSchema = z.array(projectRoleAssignmentSchema);

export const accessPolicyGrantSchema = z.object({
	scope: z.enum(['project', 'target']).nullable(),
	pipelines: z.array(z.string()),
	permissions: z.array(z.string())
});

export const accessPolicyRoleSchema = z.object({
	name: z.string(),
	description: z.string().nullable(),
	grants: z.array(accessPolicyGrantSchema)
});

export const accessPolicySchema = z.object({
	present: z.boolean(),
	fingerprint: z.string().nullable(),
	roles: z.array(accessPolicyRoleSchema)
});
