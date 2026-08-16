import { fetchAccessPolicy } from '../_api/access-policy';
import { setAdminUserActive } from '../_api/user-activation';
import { grantAdminRole, revokeAdminRole } from '../_api/user-admin-role';
import { createAdminUser, fetchAdminUsers } from '../_api/user-collection';
import { resetAdminUserPassword } from '../_api/user-password';
import {
	grantProjectRole as requestProjectRoleGrant,
	listProjectRoles,
	revokeProjectRole as requestProjectRoleRevocation
} from '../_api/user-project-role';
import type { AdminUser, UsersAdminController, UsersAdminState } from '../types';

export function createUsersAdminState(): UsersAdminController {
	const state: UsersAdminState = $state({
		users: [],
		loading: true,
		saving: false,
		error: null,
		form: {
			username: '',
			displayName: '',
			email: '',
			authenticationSource: 'trusted_proxy',
			password: ''
		},
		policy: null,
		assignments: [],
		selectedUserId: null
	});

	async function load(): Promise<void> {
		state.loading = true;
		state.error = null;
		try {
			state.users = await fetchAdminUsers();
			state.policy = await fetchAccessPolicy().catch(() => null);
		} catch (error) {
			state.error = message(error);
		} finally {
			state.loading = false;
		}
	}

	async function create(): Promise<void> {
		state.saving = true;
		state.error = null;
		try {
			const created: AdminUser = await createAdminUser({
				username: state.form.username,
				displayName: state.form.displayName || null,
				email: state.form.email || null,
				authenticationSource: state.form.authenticationSource,
				password: state.form.authenticationSource === 'password' ? state.form.password : null
			});
			state.users = [...state.users, created].sort((a, b) => a.username.localeCompare(b.username));
			state.form.username = '';
			state.form.displayName = '';
			state.form.email = '';
			state.form.password = '';
		} catch (error) {
			state.error = message(error);
		} finally {
			state.saving = false;
		}
	}

	async function toggleActive(user: AdminUser): Promise<void> {
		await replace(user.id, () => setAdminUserActive(user.id, !user.active));
	}

	async function toggleAdmin(user: AdminUser): Promise<void> {
		await replace(user.id, () =>
			user.roles.includes('admin') ? revokeAdminRole(user.id) : grantAdminRole(user.id)
		);
	}

	async function resetPassword(user: AdminUser, password: string): Promise<boolean> {
		state.error = null;
		try {
			await resetAdminUserPassword(user.id, password);
			return true;
		} catch (error) {
			state.error = message(error);
			return false;
		}
	}

	async function replace(userId: string, operation: () => Promise<AdminUser>): Promise<void> {
		state.error = null;
		try {
			const updated: AdminUser = await operation();
			state.users = state.users.map((user) => (user.id === userId ? updated : user));
		} catch (error) {
			state.error = message(error);
		}
	}

	async function selectUser(userId: string, projectName: string): Promise<void> {
		state.selectedUserId = userId;
		state.assignments = [];
		state.error = null;
		try {
			state.assignments = await listProjectRoles(userId, projectName);
		} catch (error) {
			state.error = message(error);
		}
	}

	async function grantProjectRole(
		projectName: string,
		role: string,
		targetName: string | null
	): Promise<void> {
		if (state.selectedUserId === null) return;
		state.error = null;
		try {
			await requestProjectRoleGrant(state.selectedUserId, projectName, role, targetName);
			state.assignments = await listProjectRoles(state.selectedUserId, projectName);
		} catch (error) {
			state.error = message(error);
		}
	}

	async function revokeAssignment(assignmentId: string, projectName: string): Promise<void> {
		if (state.selectedUserId === null) return;
		state.error = null;
		try {
			await requestProjectRoleRevocation(assignmentId);
			state.assignments = await listProjectRoles(state.selectedUserId, projectName);
		} catch (error) {
			state.error = message(error);
		}
	}

	return {
		state,
		load,
		create,
		toggleActive,
		toggleAdmin,
		resetPassword,
		selectUser,
		grantProjectRole,
		revokeAssignment
	};
}

function message(error: unknown): string {
	return error instanceof Error ? error.message : String(error);
}
