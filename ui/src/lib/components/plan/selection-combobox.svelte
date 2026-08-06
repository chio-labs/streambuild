<script lang="ts">
	import SearchIcon from '@lucide/svelte/icons/search';
	import XIcon from '@lucide/svelte/icons/x';
	import { selectorToken } from '$lib/domain/derive';
	import type { Project, Selector } from '$lib/domain/types';

	type Props = {
		project: Project;
		selectors: Selector[];
		onchange: (next: Selector[]) => void;
	};
	let { project, selectors, onchange }: Props = $props();

	// ONE control, not two. `main`'s run panel had an editable command line AND a
	// selector query input, both writing the same state — two controls fighting
	// over one value. Here the command string is a read-only receipt.
	//
	// A text-command input would also buy nothing: `plan`/`build` accept only a
	// bare model name or `pipeline:<name>`, and StreamBuild has no tags, groups or
	// globs to query on. This is a finite checklist, so it gets a picker.
	let query = $state<string>('');
	let open = $state<boolean>(false);

	type Option = {
		selector: Selector;
		token: string;
		primary: string;
		secondary: string;
		group: 'Pipelines' | 'Models';
	};

	const allOptions = $derived.by((): Option[] => {
		const pipelines: Option[] = project.pipelines.map((pipeline) => ({
			selector: { kind: 'pipeline', name: pipeline.name },
			token: `pipeline:${pipeline.name}`,
			primary: `pipeline:${pipeline.name}`,
			secondary: `${pipeline.models.length} models`,
			group: 'Pipelines'
		}));
		const models: Option[] = project.models.map((model) => ({
			selector: { kind: 'model', name: model.name },
			token: model.name,
			primary: model.name,
			secondary: `${model.pipeline} · ${model.storage.engine ?? 'view'}`,
			group: 'Models'
		}));
		return [...pipelines, ...models];
	});

	const chosen = $derived(new Set(selectors.map(selectorToken)));

	const matches = $derived.by((): Option[] => {
		const needle: string = query.trim().toLowerCase();
		return allOptions
			.filter((option) => !chosen.has(option.token))
			.filter(
				(option) =>
					needle === '' ||
					option.primary.toLowerCase().includes(needle) ||
					option.secondary.toLowerCase().includes(needle)
			)
			.slice(0, 12);
	});

	function add(option: Option): void {
		onchange([...selectors, option.selector]);
		query = '';
		open = false;
	}

	function remove(token: string): void {
		onchange(selectors.filter((selector) => selectorToken(selector) !== token));
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Enter' && matches.length > 0) {
			event.preventDefault();
			add(matches[0]);
			return;
		}
		if (event.key === 'Backspace' && query === '' && selectors.length > 0) {
			remove(selectorToken(selectors[selectors.length - 1]));
			return;
		}
		if (event.key === 'Escape') open = false;
	}
</script>

<div class="relative">
	<div
		class="bg-[var(--sb-inset)] flex flex-wrap items-center gap-1.5 rounded-[4px] border border-border px-2 py-2 focus-within:border-[var(--primary)]"
	>
		{#each selectors as selector (selectorToken(selector))}
			{@const token = selectorToken(selector)}
			<span
				class="flex items-center gap-1.5 rounded-[3px] border px-2 py-1 font-mono text-[11px]"
				style:border-color={selector.kind === 'pipeline' ? 'var(--primary)' : 'var(--border-strong)'}
				style:background={selector.kind === 'pipeline' ? 'var(--sidebar-accent)' : 'transparent'}
			>
				{token}
				<button
					class="text-muted-foreground hover:text-foreground"
					aria-label="Remove {token}"
					onclick={() => remove(token)}><XIcon size={11} /></button
				>
			</span>
		{/each}
		<div class="flex min-w-[180px] flex-1 items-center gap-1.5">
			<SearchIcon size={12} class="text-[var(--sb-text-faint)] shrink-0" />
			<input
				bind:value={query}
				onfocus={() => (open = true)}
				onkeydown={onKeydown}
				placeholder={selectors.length ? 'add another…' : 'pick pipelines or models…'}
				class="min-w-0 flex-1 bg-transparent py-0.5 font-mono text-[11.5px] outline-none"
			/>
		</div>
	</div>

	{#if open && matches.length}
		<div
			class="bg-popover absolute left-0 right-0 top-full z-30 mt-1 max-h-[320px] overflow-y-auto rounded-[4px] border border-border shadow-lg"
		>
			{#each ['Pipelines', 'Models'] as group (group)}
				{@const groupMatches = matches.filter((option) => option.group === group)}
				{#if groupMatches.length}
					<div
						class="text-[var(--sb-text-faint)] bg-[var(--sb-surface-low)] px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						{group}
					</div>
					{#each groupMatches as option (option.token)}
						<button
							class="hover:bg-[var(--sb-hover)] flex w-full items-center gap-2.5 px-2.5 py-1.5 text-left"
							onclick={() => add(option)}
						>
							<span class="code truncate text-[11.5px]">{option.primary}</span>
							<span class="text-muted-foreground ml-auto shrink-0 font-mono text-[10px]"
								>{option.secondary}</span
							>
						</button>
					{/each}
				{/if}
			{/each}
		</div>
	{/if}
</div>

{#if open}
	<!-- click-away -->
	<button
		class="fixed inset-0 z-20 cursor-default"
		aria-label="Close selection list"
		tabindex="-1"
		onclick={() => (open = false)}
	></button>
{/if}
