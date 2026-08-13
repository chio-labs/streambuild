import type { z } from 'zod';
import type {
	accessPolicySchema,
	adminUserSchema,
	projectRoleAssignmentSchema
} from './schemas';

export type AdminUser = z.infer<typeof adminUserSchema>;
export type ProjectRoleAssignment = z.infer<typeof projectRoleAssignmentSchema>;
export type AccessPolicy = z.infer<typeof accessPolicySchema>;

export type CreateAdminUserInput = {
	username: string;
	displayName: string | null;
	email: string | null;
	authenticationSource: 'password' | 'trusted_proxy';
	password: string | null;
};

export type CreateUserForm = {
	username: string;
	displayName: string;
	email: string;
	authenticationSource: 'password' | 'trusted_proxy';
	password: string;
};

export type UsersAdminState = {
	users: AdminUser[];
	loading: boolean;
	saving: boolean;
	error: string | null;
	form: CreateUserForm;
	policy: AccessPolicy | null;
	assignments: ProjectRoleAssignment[];
	selectedUserId: string | null;
};

export type UsersAdminController = {
	readonly state: UsersAdminState;
	load(): Promise<void>;
	create(): Promise<void>;
	toggleActive(user: AdminUser): Promise<void>;
	toggleAdmin(user: AdminUser): Promise<void>;
	resetPassword(user: AdminUser, password: string): Promise<boolean>;
	selectUser(userId: string, projectName: string): Promise<void>;
	grantProjectRole(projectName: string, role: string, targetName: string | null): Promise<void>;
	revokeAssignment(assignmentId: string, projectName: string): Promise<void>;
};
