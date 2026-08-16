<script lang="ts">
	import './layout.css';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { getAuth } from '$lib/auth/main/get-auth';
	import { initializeAuth } from '$lib/auth/main/initialize-auth';
	import AppSidebar from '$lib/presentation/components/app-sidebar.svelte';
	import CompileErrorScreen from '$lib/presentation/components/compile-error-screen.svelte';
	import { getApp } from '$lib/api/main/project/get-app';
	import { initializeApp } from '$lib/api/main/project/initialize-app';

	let { children } = $props();
	const app = getApp();
	const auth = getAuth();

	$effect(() => {
		if (auth.phase === 'unauthenticated' && page.url.pathname !== '/login') {
			void goto('/login');
		} else if (auth.phase === 'authenticated' && page.url.pathname === '/login') {
			void goto('/');
		}
	});

	onMount(async () => {
		await initializeAuth();
		if (auth.phase === 'authenticated') await initializeApp();
	});
</script>

<svelte:head>
	<link rel="icon" href="/favicon.png" />
	{#if app.phase !== 'ready'}
		<title>StreamBuild</title>
	{/if}
</svelte:head>

{#if auth.phase === 'unauthenticated' && page.url.pathname !== '/login'}
	<div class="text-muted-foreground grid h-screen place-items-center font-mono text-[13px]">
		redirecting to sign in…
	</div>
{:else if page.url.pathname === '/login'}
	{@render children()}
{:else if auth.phase === 'error'}
	<div class="grid h-screen place-items-center p-6 text-center">
		<div>
			<div class="font-display text-[17px] font-semibold">Authentication unavailable</div>
			<div class="text-muted-foreground mt-2 max-w-lg font-mono text-[11px]">{auth.error}</div>
		</div>
	</div>
{:else if auth.phase === 'loading'}
	<div class="text-muted-foreground grid h-screen place-items-center font-mono text-[13px]">authenticating…</div>
{:else if app.phase === 'ready'}
	<div class="flex h-screen overflow-hidden">
		<AppSidebar />
		<div class="flex min-w-0 flex-1 flex-col">
			{@render children()}
		</div>
	</div>
{:else if app.phase === 'compile_failing'}
	<CompileErrorScreen />
{:else if app.phase === 'unreachable'}
	<div class="text-muted-foreground grid h-screen place-items-center font-mono text-[13px]">
		<div class="flex flex-col items-center gap-2">
			<div>stb dev is not reachable</div>
			<div class="text-[var(--sb-text-faint)] text-[11px]">{app.fetchError}</div>
		</div>
	</div>
{:else}
	<div class="text-muted-foreground grid h-screen place-items-center font-mono text-[13px]">
		loading project…
	</div>
{/if}
