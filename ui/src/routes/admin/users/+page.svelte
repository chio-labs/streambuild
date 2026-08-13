<script lang="ts">
	import { onMount } from 'svelte';
	import ShieldIcon from '@lucide/svelte/icons/shield';
	import UserPlusIcon from '@lucide/svelte/icons/user-plus';
	import AppTopbar from '$lib/presentation/components/app-topbar.svelte';
	import { getAuth } from '$lib/auth/main/get-auth';
	import { sourceLabel } from './_helpers/source-label';
	import { createUsersAdminState } from './_state/users-admin.state.svelte';
	import type { AdminUser } from './types';

	const users = createUsersAdminState();
	const auth = getAuth();
	const projectName = $derived(auth.capabilities?.project ?? '');
	let grantRole = $state('');
	let grantTarget = $state('');
	const policyRoleNames = $derived((users.state.policy?.roles ?? []).map((role) => role.name));
	const selectedUser = $derived(
		users.state.users.find((user) => user.id === users.state.selectedUserId) ?? null
	);

	function grantSummary(grant: {
		scope: 'project' | 'target' | null;
		pipelines: string[];
		permissions: string[];
	}): string {
		const scope: string = grant.scope ?? `pipelines: ${grant.pipelines.join(', ')}`;
		return `${scope} → ${grant.permissions.join(', ')}`;
	}

	async function submitGrant(): Promise<void> {
		if (!grantRole) return;
		await users.grantProjectRole(projectName, grantRole, grantTarget.trim() || null);
	}
	let resetUser = $state<AdminUser | null>(null);
	let resetPassword = $state('');
	let resetConfirmation = $state('');
	let resetError = $state<string | null>(null);
	let resetting = $state(false);
	onMount(() => void users.load());

	function openPasswordReset(user: AdminUser): void {
		resetUser = user;
		resetPassword = '';
		resetConfirmation = '';
		resetError = null;
	}

	function closePasswordReset(): void {
		if (!resetting) resetUser = null;
	}

	async function submitPasswordReset(): Promise<void> {
		if (!resetUser) return;
		if (resetPassword.length < 12) {
			resetError = 'Password must be at least 12 characters.';
			return;
		}
		if (resetPassword !== resetConfirmation) {
			resetError = 'Passwords do not match.';
			return;
		}

		resetting = true;
		resetError = null;
		const succeeded: boolean = await users.resetPassword(resetUser, resetPassword);
		resetting = false;
		if (succeeded) resetUser = null;
	}
</script>

<AppTopbar title="Users" breadcrumb="System administration" />

<div class="min-h-0 flex-1 overflow-y-auto">
	<div class="grid gap-5 p-[18px] lg:grid-cols-[minmax(0,1fr)_340px]">
		<section class="overflow-hidden rounded-md border border-border bg-card">
			<div class="flex items-center gap-2 border-b border-border px-4 py-3">
				<ShieldIcon size={14} class="text-primary" />
				<h2 class="font-display text-[14px] font-semibold">Accounts</h2>
				<span class="text-muted-foreground ml-auto font-mono text-[10px]">{users.state.users.length} users</span>
			</div>
			{#if users.state.loading}
				<div class="text-muted-foreground p-6 font-mono text-[12px]">loading accounts…</div>
			{:else}
				<div class="overflow-x-auto">
					<table class="sb-list w-full text-left">
						<thead><tr class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.12em]"><th class="px-4 py-2 font-normal">User</th><th class="px-4 py-2 font-normal">Source</th><th class="px-4 py-2 font-normal">Roles</th><th class="px-4 py-2 font-normal">Status</th><th class="px-4 py-2 font-normal"></th></tr></thead>
						<tbody>
							{#each users.state.users as user (user.id)}
								<tr>
									<td class="px-4 py-2.5"><div class="font-mono text-[12px]">{user.username}</div><div class="text-muted-foreground text-[10.5px]">{user.displayName ?? user.email ?? ''}</div></td>
									<td class="text-muted-foreground px-4 font-mono text-[10.5px]">{sourceLabel(user)}</td>
									<td class="px-4 font-mono text-[10.5px]">{user.roles.join(', ')}</td>
									<td class="px-4"><span class={user.active ? 'text-[var(--sb-success)]' : 'text-[var(--sb-error)]'}>{user.active ? 'active' : 'disabled'}</span></td>
									<td class="px-4"><div class="flex justify-end gap-1.5">{#if user.authenticationSources.includes('password')}<button class="rounded border border-border px-2 py-1 font-mono text-[10px] hover:bg-[var(--sb-hover)]" onclick={() => openPasswordReset(user)}>reset password</button>{/if}<button class="rounded border border-border px-2 py-1 font-mono text-[10px] hover:bg-[var(--sb-hover)]" onclick={() => void users.toggleAdmin(user)}>{user.roles.includes('admin') ? 'remove admin' : 'make admin'}</button><button class="rounded border border-border px-2 py-1 font-mono text-[10px] hover:bg-[var(--sb-hover)]" onclick={() => void users.toggleActive(user)}>{user.active ? 'disable' : 'enable'}</button></div></td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>

		<section class="h-fit rounded-md border border-border bg-card">
			<div class="flex items-center gap-2 border-b border-border px-4 py-3"><UserPlusIcon size={14} class="text-primary" /><h2 class="font-display text-[14px] font-semibold">Create account</h2></div>
			<form class="space-y-3 p-4" onsubmit={(event) => { event.preventDefault(); void users.create(); }}>
				<label class="block"><span class="text-muted-foreground mb-1 block font-mono text-[10px] uppercase">Username</span><input class="h-8 w-full rounded border border-input bg-background px-2.5 font-mono text-[12px]" bind:value={users.state.form.username} required /></label>
				<label class="block"><span class="text-muted-foreground mb-1 block font-mono text-[10px] uppercase">Display name</span><input class="h-8 w-full rounded border border-input bg-background px-2.5 text-[12px]" bind:value={users.state.form.displayName} /></label>
				<label class="block"><span class="text-muted-foreground mb-1 block font-mono text-[10px] uppercase">Email</span><input class="h-8 w-full rounded border border-input bg-background px-2.5 text-[12px]" type="email" bind:value={users.state.form.email} /></label>
				<label class="block"><span class="text-muted-foreground mb-1 block font-mono text-[10px] uppercase">Authentication</span><select class="h-8 w-full rounded border border-input bg-background px-2.5 text-[12px]" bind:value={users.state.form.authenticationSource}><option value="trusted_proxy">Trusted proxy</option><option value="password">Password</option></select></label>
				{#if users.state.form.authenticationSource === 'password'}<label class="block"><span class="text-muted-foreground mb-1 block font-mono text-[10px] uppercase">Initial password</span><input class="h-8 w-full rounded border border-input bg-background px-2.5 text-[12px]" type="password" minlength="12" bind:value={users.state.form.password} required /></label>{/if}
				<button class="h-8 w-full rounded bg-primary font-mono text-[11px] font-medium text-primary-foreground disabled:opacity-60" disabled={users.state.saving}>{users.state.saving ? 'creating…' : 'create viewer account'}</button>
			</form>
		</section>
	</div>

	<div class="grid gap-5 px-[18px] pb-[18px] lg:grid-cols-[minmax(0,1fr)_340px]">
		<section class="overflow-hidden rounded-md border border-border bg-card">
			<div class="flex items-center gap-2 border-b border-border px-4 py-3">
				<ShieldIcon size={14} class="text-primary" />
				<h2 class="font-display text-[14px] font-semibold">Project roles</h2>
				<span class="text-muted-foreground ml-auto font-mono text-[10px]">{projectName}</span>
			</div>
			<div class="space-y-3 p-4">
				<label class="block max-w-xs">
					<span class="text-muted-foreground mb-1 block font-mono text-[10px] uppercase">User</span>
					<select
						class="h-8 w-full rounded border border-input bg-background px-2.5 text-[12px]"
						aria-label="Project role user"
						onchange={(event) =>
							void users.selectUser((event.currentTarget as HTMLSelectElement).value, projectName)}
					>
						<option value="" selected={selectedUser === null}>select a user…</option>
						{#each users.state.users as user (user.id)}
							<option value={user.id} selected={user.id === users.state.selectedUserId}
								>{user.username}</option
							>
						{/each}
					</select>
				</label>
				{#if selectedUser !== null}
					{#if users.state.assignments.length === 0}
						<p class="text-muted-foreground font-mono text-[11px]">
							No project roles assigned to {selectedUser.username}.
						</p>
					{:else}
						<table class="sb-list w-full text-left">
							<thead
								><tr
									class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.12em]"
									><th class="py-1.5 pr-3 font-normal">Role</th><th class="py-1.5 pr-3 font-normal"
										>Target</th
									><th class="py-1.5 pr-3 font-normal">Status</th><th class="py-1.5 font-normal"
									></th></tr
								></thead
							>
							<tbody>
								{#each users.state.assignments as assignment (assignment.assignmentId)}
									<tr>
										<td class="py-1.5 pr-3 font-mono text-[11px]">{assignment.role}</td>
										<td class="py-1.5 pr-3 font-mono text-[11px]"
											>{assignment.targetName ?? 'all targets'}</td
										>
										<td class="py-1.5 pr-3 font-mono text-[11px]">
											{#if policyRoleNames.includes(assignment.role)}
												<span class="text-[var(--sb-success)]">active</span>
											{:else}
												<span
													class="text-[var(--sb-warning)]"
													title="This role no longer exists in access.yml and does not authorize anything"
													>stale</span
												>
											{/if}
										</td>
										<td class="py-1.5 text-right">
											<button
												class="rounded border border-border px-2 py-1 font-mono text-[10px] hover:bg-[var(--sb-hover)]"
												onclick={() =>
													void users.revokeAssignment(assignment.assignmentId, projectName)}
												>revoke</button
											>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					{/if}
					<form
						class="flex flex-wrap items-end gap-2"
						onsubmit={(event) => {
							event.preventDefault();
							void submitGrant();
						}}
					>
						<label class="block">
							<span class="text-muted-foreground mb-1 block font-mono text-[10px] uppercase"
								>Role</span
							>
							<select
								class="h-8 rounded border border-input bg-background px-2.5 text-[12px]"
								aria-label="Project role name"
								bind:value={grantRole}
								required
							>
								<option value="">select a compiled role…</option>
								{#each policyRoleNames as roleName (roleName)}
									<option value={roleName}>{roleName}</option>
								{/each}
							</select>
						</label>
						<label class="block">
							<span class="text-muted-foreground mb-1 block font-mono text-[10px] uppercase"
								>Target (empty = all targets)</span
							>
							<input
								class="h-8 rounded border border-input bg-background px-2.5 font-mono text-[12px]"
								aria-label="Assignment target"
								bind:value={grantTarget}
								placeholder="all targets"
							/>
						</label>
						<button
							class="h-8 rounded bg-primary px-3 font-mono text-[11px] font-medium text-primary-foreground disabled:opacity-60"
							disabled={!grantRole}>assign role</button
						>
					</form>
				{/if}
			</div>
		</section>

		<section class="h-fit rounded-md border border-border bg-card">
			<div class="flex items-center gap-2 border-b border-border px-4 py-3">
				<ShieldIcon size={14} class="text-primary" />
				<h2 class="font-display text-[14px] font-semibold">Compiled roles</h2>
			</div>
			<div class="space-y-3 p-4">
				{#if users.state.policy === null || !users.state.policy.present}
					<p class="text-muted-foreground font-mono text-[11px]">
						No access.yml policy is compiled. Only system administrators can operate.
					</p>
				{:else}
					{#each users.state.policy.roles as role (role.name)}
						<div class="rounded border border-border p-2.5">
							<div class="font-mono text-[12px]">{role.name}</div>
							{#if role.description}
								<div class="text-muted-foreground text-[11px]">{role.description}</div>
							{/if}
							{#each role.grants as grant, grantIndex (grantIndex)}
								<div class="text-[var(--sb-text-faint)] font-mono text-[10.5px]">
									{grantSummary(grant)}
								</div>
							{/each}
						</div>
					{/each}
					<p class="text-[var(--sb-text-faint)] font-mono text-[10px]">
						Roles are defined in access.yml and are read-only here.
					</p>
				{/if}
			</div>
		</section>
	</div>
	{#if users.state.error}<div class="fixed bottom-5 right-5 max-w-md rounded-md border border-[var(--sb-error)] bg-card px-4 py-3 text-[12px] text-[var(--sb-error)] shadow-[var(--sb-elev)]">{users.state.error}</div>{/if}
</div>

{#if resetUser}
	<dialog open class="fixed inset-0 z-50 h-full w-full max-w-none place-items-center bg-black/55 p-4 open:grid" aria-labelledby="reset-password-title">
		<section class="w-full max-w-md rounded-md border border-border bg-card text-foreground shadow-[var(--sb-elev)]">
			<div class="border-b border-border px-4 py-3">
				<h2 id="reset-password-title" class="font-display text-[14px] font-semibold">Reset {resetUser.username}'s password</h2>
			</div>
			<form class="space-y-3 p-4" onsubmit={(event) => { event.preventDefault(); void submitPasswordReset(); }}>
				<label class="block"><span class="text-muted-foreground mb-1 block font-mono text-[10px] uppercase">New password</span><input class="h-8 w-full rounded border border-input bg-background px-2.5 text-[12px]" type="password" minlength="12" autocomplete="new-password" bind:value={resetPassword} required /></label>
				<label class="block"><span class="text-muted-foreground mb-1 block font-mono text-[10px] uppercase">Confirm password</span><input class="h-8 w-full rounded border border-input bg-background px-2.5 text-[12px]" type="password" minlength="12" autocomplete="new-password" bind:value={resetConfirmation} required /></label>
				{#if resetError}<p class="text-[11px] text-[var(--sb-error)]">{resetError}</p>{/if}
				<div class="flex justify-end gap-2 pt-1">
					<button type="button" class="h-8 rounded border border-border px-3 font-mono text-[11px] hover:bg-[var(--sb-hover)]" onclick={closePasswordReset} disabled={resetting}>cancel</button>
					<button class="h-8 rounded bg-primary px-3 font-mono text-[11px] font-medium text-primary-foreground disabled:opacity-60" disabled={resetting}>{resetting ? 'resetting…' : 'reset password'}</button>
				</div>
			</form>
		</section>
	</dialog>
{/if}
