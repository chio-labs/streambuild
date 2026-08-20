import type { z } from 'zod';
import type {
	authConfigSchema,
	authenticatedUserSchema,
	authenticationModeSchema,
	authPayloadSchema,
	capabilitiesSchema
} from './schemas';

export type AuthenticationMode = z.infer<typeof authenticationModeSchema>;
export type AuthenticatedUser = z.infer<typeof authenticatedUserSchema>;
export type AuthConfig = z.infer<typeof authConfigSchema>;
export type AuthPayload = z.infer<typeof authPayloadSchema>;
export type Capabilities = z.infer<typeof capabilitiesSchema>;

export type AuthPhase = 'loading' | 'authenticated' | 'unauthenticated' | 'error';

export type AuthState = {
	phase: AuthPhase;
	config: AuthConfig | null;
	user: AuthenticatedUser | null;
	roles: string[];
	csrfToken: string | null;
	capabilities: Capabilities | null;
	error: string | null;
};

export type AuthController = {
	readonly auth: AuthState;
	initialize(): Promise<void>;
	initializeFromBootstrap(
		config: AuthConfig,
		payload: AuthPayload,
		capabilities: Capabilities | null
	): void;
	login(username: string, password: string): Promise<void>;
	logout(): Promise<void>;
	markUnauthenticated(): void;
};
