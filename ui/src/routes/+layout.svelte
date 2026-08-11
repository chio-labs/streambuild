<script lang="ts">
	import './layout.css';
	import { onMount } from 'svelte';
	import AppSidebar from '$lib/presentation/components/app-sidebar.svelte';
	import CompileErrorScreen from '$lib/presentation/components/compile-error-screen.svelte';
	import { getApp } from '$lib/api/main/project/get-app';
	import { initializeApp } from '$lib/api/main/project/initialize-app';

	let { children } = $props();
	const app = getApp();

	onMount(() => {
		void initializeApp();
	});
</script>

<svelte:head>
	<link rel="icon" href="/favicon.png" />
	{#if app.phase !== 'ready'}
		<title>StreamBuild</title>
	{/if}
</svelte:head>

{#if app.phase === 'ready'}
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
