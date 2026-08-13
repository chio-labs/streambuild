import { z } from 'zod';

export const authenticationModeSchema = z.enum(['disabled', 'password', 'trusted_proxy']);

export const authenticatedUserSchema = z.object({
	id: z.uuid(),
	username: z.string(),
	displayName: z.string().nullable(),
	email: z.string().nullable(),
	authenticationSource: z.enum(['local', 'password', 'trusted_proxy'])
});

export const authConfigSchema = z.object({
	mode: authenticationModeSchema,
	loginRequired: z.boolean(),
	proxyLogoutUrl: z.string().nullable()
});

export const authPayloadSchema = z.object({
	mode: authenticationModeSchema,
	user: authenticatedUserSchema,
	roles: z.array(z.string()),
	csrfToken: z.string().nullable()
});

export const authErrorPayloadSchema = z.object({ detail: z.string().optional() });
export const authOkStatusSchema = z.object({ status: z.literal('ok') });

export const capabilitiesSchema = z.object({
	systemAdmin: z.boolean(),
	project: z.string(),
	target: z.string().nullable(),
	permissions: z.array(z.string()),
	pipelinePermissions: z.record(z.string(), z.array(z.string())),
	staleRoles: z.array(z.string())
});
