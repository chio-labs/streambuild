<script lang="ts">
	import KeyRoundIcon from '@lucide/svelte/icons/key-round';
	import { createLoginState } from './state.svelte';

	const login = createLoginState();
</script>

<svelte:head><title>Sign in · StreamBuild</title></svelte:head>

<main class="grid min-h-screen place-items-center bg-background p-6">
	<section class="w-full max-w-[390px] overflow-hidden rounded-lg border border-border bg-card shadow-[var(--sb-elev)]">
		<div class="border-b border-border px-7 py-6">
			<div class="mb-5 flex items-center gap-3">
				<div class="grid h-9 w-9 place-items-center rounded-md bg-primary text-primary-foreground">
					<KeyRoundIcon size={17} />
				</div>
				<div>
					<h1 class="font-display text-[18px] font-semibold">StreamBuild</h1>
					<p class="text-muted-foreground font-mono text-[10px] uppercase tracking-[0.15em]">Control plane</p>
				</div>
			</div>
			<h2 class="font-display text-[15px] font-medium">Sign in to continue</h2>
			<p class="text-muted-foreground mt-1 text-[12px]">Use the account created by your StreamBuild administrator.</p>
		</div>

		<form class="space-y-4 px-7 py-6" onsubmit={(event) => { event.preventDefault(); void login.submit(); }}>
			<label class="block">
				<span class="text-muted-foreground mb-1.5 block font-mono text-[10px] uppercase tracking-[0.12em]">Username</span>
				<input class="h-9 w-full rounded-md border border-input bg-background px-3 font-mono text-[13px] outline-none focus:border-primary" bind:value={login.form.username} autocomplete="username" required />
			</label>
			<label class="block">
				<span class="text-muted-foreground mb-1.5 block font-mono text-[10px] uppercase tracking-[0.12em]">Password</span>
				<input class="h-9 w-full rounded-md border border-input bg-background px-3 text-[13px] outline-none focus:border-primary" type="password" bind:value={login.form.password} autocomplete="current-password" required />
			</label>
			{#if login.form.error}
				<p class="rounded-md border border-[color-mix(in_srgb,var(--sb-error)_35%,transparent)] bg-[color-mix(in_srgb,var(--sb-error)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--sb-error)]">{login.form.error}</p>
			{/if}
			<button class="h-9 w-full rounded-md bg-primary font-mono text-[12px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-60" disabled={login.form.submitting}>
				{login.form.submitting ? 'signing in…' : 'sign in'}
			</button>
		</form>
	</section>
</main>
