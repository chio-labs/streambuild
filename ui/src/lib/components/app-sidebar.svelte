<script lang="ts">
	import { page } from '$app/state';
	import ActivityIcon from '@lucide/svelte/icons/activity';
	import NetworkIcon from '@lucide/svelte/icons/network';
	import WorkflowIcon from '@lucide/svelte/icons/workflow';
	import LibraryIcon from '@lucide/svelte/icons/library';
	import RadioIcon from '@lucide/svelte/icons/radio';
	import ReplaceIcon from '@lucide/svelte/icons/replace';
	import ShieldCheckIcon from '@lucide/svelte/icons/shield-check';
	import ServerIcon from '@lucide/svelte/icons/server';
	import SettingsIcon from '@lucide/svelte/icons/settings';
	import type { Icon as IconType } from '@lucide/svelte';
	import { getProject } from '$lib/api';
	import type { Project } from '$lib/domain/types';

	type NavItem = { label: string; href: string; icon: typeof IconType };
	type NavGroup = { section: string; items: NavItem[] };

	const project: Project = getProject();

	// Two sections only. `main`'s Operate group (Runs / Jobs / Triggers) has no
	// StreamBuild counterpart: there is no scheduler and no run history.
	const groups: NavGroup[] = [
		{
			section: 'Flow',
			items: [
				{ label: 'Overview', href: '/', icon: ActivityIcon },
				{ label: 'Lineage', href: '/lineage', icon: NetworkIcon },
				{ label: 'Pipelines', href: '/pipelines', icon: WorkflowIcon },
				{ label: 'Catalog', href: '/catalog', icon: LibraryIcon },
				{ label: 'Sources', href: '/sources', icon: RadioIcon }
			]
		},
		{
			section: 'Change',
			items: [
				{ label: 'Plan', href: '/plan', icon: ReplaceIcon },
				{ label: 'Quality', href: '/quality', icon: ShieldCheckIcon }
			]
		}
	];

	const footerItems: NavItem[] = [
		{ label: 'Deployment', href: '/deployment', icon: ServerIcon },
		{ label: 'Settings', href: '/settings', icon: SettingsIcon }
	];

	function isActive(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname.startsWith(href);
	}
</script>

<aside
	class="bg-sidebar flex h-screen w-56 shrink-0 flex-col border-r border-[var(--sidebar-border)] px-2.5 py-3.5"
>
	<div class="flex items-center gap-2 px-2 pb-4">
		<!-- Official StreamBuild wordmark from the docs repo. Two files rather than
		     one recoloured asset, because the mark's yellow stays constant while the
		     wordmark inverts. -->
		<img src="/logo-on-dark.png" alt="StreamBuild" class="logo-dark h-[24px] w-auto" />
		<img src="/logo-on-light.png" alt="StreamBuild" class="logo-light h-[24px] w-auto" />
	</div>

	<div
		class="text-[var(--sb-text-faint)] px-2.5 pb-1.5 pt-2 font-mono text-[10px] uppercase tracking-[0.16em]"
	>
		Project
	</div>
	<div class="mx-1 mb-1 flex items-center gap-2.5 px-2.5 py-1.5 text-[13px] font-medium">
		<span class="bg-[var(--sb-secondary)] h-1.5 w-1.5 rounded-[2px]"></span>
		{project.name}
	</div>
	<!-- Mode is config-based and single-valued, so it is a label and never a switcher. -->
	<div class="text-[var(--sb-text-faint)] mx-1 mb-3 px-2.5 font-mono text-[10px]">
		direct mode · {project.adapter}
	</div>

	<nav class="flex flex-1 flex-col gap-px">
		{#each groups as group (group.section)}
			<div
				class="text-[var(--sb-text-faint)] px-3 pb-1 pt-3.5 font-mono text-[10px] uppercase tracking-[0.16em]"
			>
				{group.section}
			</div>
			{#each group.items as item (item.href)}
				{@const Glyph = item.icon}
				<a
					href={item.href}
					class="relative flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] {isActive(
						item.href
					)
						? 'bg-[var(--sidebar-accent)] text-foreground before:absolute before:-left-2.5 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-r before:bg-primary before:content-[\'\']'
						: 'text-[var(--sidebar-foreground)] hover:bg-[var(--sb-hover)] hover:text-foreground'}"
				>
					<span class="grid w-4 place-items-center opacity-80"><Glyph size={14} /></span>
					{item.label}
				</a>
			{/each}
		{/each}

		<div class="flex-1"></div>

		{#each footerItems as item (item.href)}
			{@const Glyph = item.icon}
			<a
				href={item.href}
				class="text-[var(--sidebar-foreground)] hover:bg-[var(--sb-hover)] hover:text-foreground flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px]"
			>
				<span class="grid w-4 place-items-center opacity-80"><Glyph size={14} /></span>
				{item.label}
			</a>
		{/each}
	</nav>

</aside>

<style>
	/* default (light theme): show the dark-ink wordmark */
	.logo-dark {
		display: none;
	}
	.logo-light {
		display: block;
	}
	/* dark theme: show the light-ink wordmark */
	:global(.dark) .logo-dark {
		display: block;
	}
	:global(.dark) .logo-light {
		display: none;
	}
</style>
