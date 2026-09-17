<script lang="ts">
	import { onMount } from 'svelte';
	import AppTopbar from '$lib/presentation/components/app-topbar.svelte';
	import FactRow from '$lib/presentation/components/fact-row.svelte';
	import { getAuth } from '$lib/auth/main/get-auth';
	import { sourceLabel } from './_helpers/source-label';
	import { createUsersAdminState } from './_state/users-admin.state.svelte';
	import type { AdminUser } from './types';

	const users = createUsersAdminState();
	const auth = getAuth();
	const projectName = $derived(auth.capabilities?.project ?? '');
	const policyRoleNames = $derived((users.state.policy?.roles ?? []).map((role) => role.name));
	const selectedUser = $derived(
		users.state.users.find((user) => user.id === users.state.selectedUserId) ?? null
	);

	let creating = $state(false);
	let grantRole = $state('');
	let grantTarget = $state('');
	let resetUser = $state<AdminUser | null>(null);
	let resetPassword = $state('');
	let resetConfirmation = $state('');
	let resetError = $state<string | null>(null);
	let resetting = $state(false);

	onMount(() => void users.load());

	async function submitGrant(): Promise<void> {
		if (!grantRole) return;
		await users.grantProjectRole(projectName, grantRole, grantTarget.trim() || null);
		grantRole = '';
		grantTarget = '';
	}

	async function submitCreate(): Promise<void> {
		await users.create();
		if (users.state.error === null) creating = false;
	}

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

{#snippet caption(text: string)}
	<div class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]">
		{text}
	</div>
{/snippet}

{#snippet statusDot(active: boolean)}
	<span class="flex items-center gap-1.5 font-mono text-[11px]">
		<span
			class="h-[7px] w-[7px] rounded-full"
			style:background={active ? 'var(--sb-success)' : 'var(--sb-error)'}
		></span>
		{active ? 'active' : 'disabled'}
	</span>
{/snippet}

<AppTopbar title="Users" breadcrumb="System administration" />

<div class="min-h-0 flex-1 overflow-y-auto px-[18px] py-4">
	<div class="grid max-w-[1120px] gap-4" style:grid-template-columns="minmax(0,1fr) 360px">
		<div class="h-fit rounded-[4px] border border-border">
			<div class="flex items-center gap-2 border-b border-border px-3 py-2">
				{@render caption('Accounts')}
				<span class="text-[var(--sb-text-faint)] font-mono text-[10px]"
					>{users.state.users.length}</span
				>
				<button
					class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] ml-auto rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px]"
					onclick={() => (creating = !creating)}
				>
					{creating ? 'close' : 'new account'}
				</button>
			</div>
			{#if users.state.loading}
				<div class="text-[var(--sb-text-faint)] px-3 py-4 font-mono text-[11px]">
					loading accounts…
				</div>
			{:else}
				<div class="overflow-x-auto">
					<div class="min-w-[620px]">
						<div
							class="text-[var(--sb-text-faint)] grid border-b border-border bg-[var(--sb-surface-low)] font-mono text-[10px] uppercase tracking-[0.14em]"
							style:grid-template-columns="minmax(0,2fr) minmax(90px,1fr) minmax(90px,1fr) 90px"
						>
							<span class="border-r border-[var(--border-subtle)] px-3 py-1.5">User</span>
							<span class="border-r border-[var(--border-subtle)] px-3 py-1.5">Source</span>
							<span class="border-r border-[var(--border-subtle)] px-3 py-1.5">Roles</span>
							<span class="px-3 py-1.5">Status</span>
						</div>
						{#each users.state.users as user (user.id)}
							<button
								type="button"
								class="grid w-full cursor-pointer border-b border-[var(--border-subtle)] text-left hover:bg-[var(--sb-hover)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--ring)]"
								style:background={user.id === users.state.selectedUserId
									? 'var(--sb-hover)'
									: undefined}
								style:grid-template-columns="minmax(0,2fr) minmax(90px,1fr) minmax(90px,1fr) 90px"
								aria-pressed={user.id === users.state.selectedUserId}
								onclick={() => void users.selectUser(user.id, projectName)}
							>
								<span class="border-r border-[var(--border-subtle)] px-3 py-2.5">
									<span class="sr-only">Select user: </span>
									<span class="block font-mono text-[12px]">{user.username}</span>
									{#if user.displayName || user.email}
										<span class="text-[var(--sb-text-faint)] block text-[10.5px]">
											<span class="sr-only">{user.displayName ? 'Display name: ' : 'Email: '}</span>
											{user.displayName ?? user.email}
										</span>
									{/if}
								</span>
								<span
									class="text-muted-foreground flex items-center border-r border-[var(--border-subtle)] px-3 font-mono text-[10.5px]"
									data-testid={`user-row-source-${user.username}`}
								>
									<span class="sr-only">Source: </span>
									{sourceLabel(user)}
								</span>
								<span class="flex items-center border-r border-[var(--border-subtle)] px-3 font-mono text-[10.5px]">
									<span class="sr-only">Roles: </span>
									{user.roles.join(', ')}
									{#if user.roles.length === 0}<span class="sr-only">none</span>{/if}
								</span>
								<span class="flex items-center px-3">
									<span class="sr-only">Status: </span>
									{@render statusDot(user.active)}
								</span>
							</button>
						{/each}
					</div>
				</div>
			{/if}
		</div>

		<div class="h-fit rounded-[4px] border border-border p-4">
			{#if creating}
				{@render caption('New account')}
				<form
					class="space-y-3 pt-3"
					onsubmit={(event) => {
						event.preventDefault();
						void submitCreate();
					}}
				>
					<label class="block">
						<span class="text-[var(--sb-text-faint)] mb-1 block font-mono text-[10px] uppercase tracking-[0.14em]"
							>Username</span
						>
						<input
							class="h-7 w-full rounded-[4px] border border-border bg-background px-2 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
							bind:value={users.state.form.username}
							required
						/>
					</label>
					<label class="block">
						<span class="text-[var(--sb-text-faint)] mb-1 block font-mono text-[10px] uppercase tracking-[0.14em]"
							>Display name</span
						>
						<input
							class="h-7 w-full rounded-[4px] border border-border bg-background px-2 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
							bind:value={users.state.form.displayName}
						/>
					</label>
					<label class="block">
						<span class="text-[var(--sb-text-faint)] mb-1 block font-mono text-[10px] uppercase tracking-[0.14em]"
							>Email</span
						>
						<input
							class="h-7 w-full rounded-[4px] border border-border bg-background px-2 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
							type="email"
							bind:value={users.state.form.email}
						/>
					</label>
					<label class="block">
						<span class="text-[var(--sb-text-faint)] mb-1 block font-mono text-[10px] uppercase tracking-[0.14em]"
							>Authentication</span
						>
						<select
							class="h-7 w-full rounded-[4px] border border-border bg-background px-1.5 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
							bind:value={users.state.form.authenticationSource}
						>
							<option value="trusted_proxy">trusted proxy</option>
							<option value="password">password</option>
						</select>
					</label>
					{#if users.state.form.authenticationSource === 'password'}
						<label class="block">
							<span class="text-[var(--sb-text-faint)] mb-1 block font-mono text-[10px] uppercase tracking-[0.14em]"
								>Initial password</span
							>
							<input
								class="h-7 w-full rounded-[4px] border border-border bg-background px-2 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
								type="password"
								minlength="12"
								bind:value={users.state.form.password}
								required
							/>
						</label>
					{/if}
					<div class="flex items-center gap-2 pt-1">
						<button
							class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2.5 py-1 font-mono text-[10.5px] disabled:opacity-60"
							disabled={users.state.saving}
						>
							{users.state.saving ? 'creating…' : 'create viewer account'}
						</button>
						<span class="text-[var(--sb-text-faint)] font-mono text-[10px]"
							>starts as viewer</span
						>
					</div>
				</form>
			{:else if selectedUser}
				<div class="flex items-center gap-2.5 pb-1">
					<span class="font-mono text-[13px]">{selectedUser.username}</span>
					{@render statusDot(selectedUser.active)}
				</div>
				<FactRow label="source" value={sourceLabel(selectedUser)} mono />
				<FactRow label="display name" value={selectedUser.displayName ?? '—'} />
				<FactRow label="email" value={selectedUser.email ?? '—'} />
				<FactRow label="system roles" value={selectedUser.roles.join(', ')} mono />
				<div class="flex flex-wrap gap-1.5 pt-3">
					<button
						class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
						onclick={() => void users.toggleAdmin(selectedUser)}
					>
						{selectedUser.roles.includes('admin') ? 'remove admin' : 'make admin'}
					</button>
					<button
						class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
						onclick={() => void users.toggleActive(selectedUser)}
					>
						{selectedUser.active ? 'disable' : 'enable'}
					</button>
					{#if selectedUser.authenticationSources.includes('password')}
						<button
							class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
							onclick={() => openPasswordReset(selectedUser)}
						>
							reset password
						</button>
					{/if}
				</div>

				<div class="flex items-baseline gap-2 pt-5">
					{@render caption('Project roles')}
					<span class="text-[var(--sb-text-faint)] font-mono text-[10px]">{projectName}</span>
				</div>
				{#if users.state.assignments.length === 0}
					<p class="text-[var(--sb-text-faint)] pt-2 font-mono text-[11px]">
						No project roles assigned to {selectedUser.username}.
					</p>
				{:else}
					<table class="mt-1 w-full text-left">
						<tbody>
							{#each users.state.assignments as assignment (assignment.assignmentId)}
								<tr class="border-b border-[var(--border-subtle)]">
									<td class="py-2 pr-3 font-mono text-[11px]">{assignment.role}</td>
									<td class="text-muted-foreground py-2 pr-3 font-mono text-[10.5px]"
										>{assignment.targetName ?? 'all targets'}</td
									>
									<td class="py-2 pr-3 font-mono text-[10.5px]">
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
									<td class="py-2 text-right">
										<button
											class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10px]"
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
					class="space-y-2 pt-3"
					onsubmit={(event) => {
						event.preventDefault();
						void submitGrant();
					}}
				>
					<select
						class="h-7 w-full rounded-[4px] border border-border bg-background px-1.5 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
						class:text-muted-foreground={!grantRole}
						aria-label="Project role name"
						bind:value={grantRole}
						required
					>
						<option value="">role…</option>
						{#each policyRoleNames as roleName (roleName)}
							<option value={roleName}>{roleName}</option>
						{/each}
					</select>
					<div class="flex gap-1.5">
						<input
							class="h-7 min-w-0 flex-1 rounded-[4px] border border-border bg-background px-2 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
							aria-label="Assignment target"
							bind:value={grantTarget}
							placeholder="all targets"
							title="Leave empty to authorize every target"
						/>
						<button
							class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2.5 font-mono text-[10.5px] disabled:opacity-60"
							disabled={!grantRole}>assign role</button
						>
					</div>
				</form>
			{:else}
				{@render caption('Account')}
				<p class="text-[var(--sb-text-faint)] pt-2 font-mono text-[11px]">
					Select an account to manage status, system roles, and project roles.
				</p>
			{/if}
		</div>

		<div class="rounded-[4px] border border-border p-4" style:grid-column="1 / -1">
			<div class="flex items-baseline gap-2 pb-2">
				{@render caption('Compiled roles')}
				<span class="text-[var(--sb-text-faint)] font-mono text-[10px]"
					>defined in access.yml · read-only</span
				>
			</div>
			{#if users.state.policy === null || !users.state.policy.present}
				<p class="text-[var(--sb-text-faint)] font-mono text-[11px]">
					No access.yml policy is compiled. Only system administrators can operate.
				</p>
			{:else}
				<div class="grid gap-x-8 gap-y-3" style:grid-template-columns="repeat(auto-fill, minmax(320px, 1fr))">
					{#each users.state.policy.roles as role (role.name)}
						<div>
							<span class="font-mono text-[12px]">{role.name}</span>
							{#if role.description}
								<span class="text-muted-foreground pl-2 text-[11px]">{role.description}</span>
							{/if}
							{#each role.grants as grant, grantIndex (grantIndex)}
								<div class="flex items-baseline gap-3 py-[3px] font-mono text-[10.5px]">
									<span class="text-[var(--sb-text-faint)] w-40 shrink-0 truncate">
										{grant.scope ?? grant.pipelines.join(', ')}
									</span>
									<span class="text-muted-foreground min-w-0 flex-1"
										>{grant.permissions.join(', ')}</span
									>
								</div>
							{/each}
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
	{#if users.state.error}
		<div
			class="bg-background fixed bottom-5 right-5 max-w-md rounded-[4px] border border-[var(--sb-error)] px-4 py-3 font-mono text-[11px] text-[var(--sb-error)] shadow-[var(--sb-elev)]"
		>
			{users.state.error}
		</div>
	{/if}
</div>

{#if resetUser}
	<dialog
		open
		class="fixed inset-0 z-50 h-full w-full max-w-none place-items-center bg-black/55 p-4 open:grid"
		aria-labelledby="reset-password-title"
	>
		<section class="bg-background text-foreground w-full max-w-md rounded-[4px] border border-border shadow-[var(--sb-elev)]">
			<div class="border-b border-border px-4 py-3">
				<h2 id="reset-password-title" class="text-[13px] font-medium">
					Reset {resetUser.username}'s password
				</h2>
			</div>
			<form
				class="space-y-3 p-4"
				onsubmit={(event) => {
					event.preventDefault();
					void submitPasswordReset();
				}}
			>
				<label class="block">
					<span class="text-[var(--sb-text-faint)] mb-1 block font-mono text-[10px] uppercase tracking-[0.14em]"
						>New password</span
					>
					<input
						class="h-7 w-full rounded-[4px] border border-border bg-background px-2 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
						type="password"
						minlength="12"
						autocomplete="new-password"
						bind:value={resetPassword}
						required
					/>
				</label>
				<label class="block">
					<span class="text-[var(--sb-text-faint)] mb-1 block font-mono text-[10px] uppercase tracking-[0.14em]"
						>Confirm password</span
					>
					<input
						class="h-7 w-full rounded-[4px] border border-border bg-background px-2 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
						type="password"
						minlength="12"
						autocomplete="new-password"
						bind:value={resetConfirmation}
						required
					/>
				</label>
				{#if resetError}
					<p class="font-mono text-[11px] text-[var(--sb-error)]">{resetError}</p>
				{/if}
				<div class="flex justify-end gap-2 pt-1">
					<button
						type="button"
						class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2.5 py-1 font-mono text-[10.5px]"
						onclick={closePasswordReset}
						disabled={resetting}>cancel</button
					>
					<button
						class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2.5 py-1 font-mono text-[10.5px] disabled:opacity-60"
						disabled={resetting}>{resetting ? 'resetting…' : 'reset password'}</button
					>
				</div>
			</form>
		</section>
	</dialog>
{/if}
