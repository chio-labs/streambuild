<script lang="ts">
	import XIcon from '@lucide/svelte/icons/x';
	import { untrack } from 'svelte';
	import { formatCompact } from '$lib/formatting/main/format-compact';
	import ChipEditor from '$lib/message-browser/components/chip-editor.svelte';
	import { predicateLabel } from '$lib/message-browser/_helpers/filter-document';
	import type {
		MessageBrowserState,
		MessageFilterDocument,
		MessageMode,
		MessageModeKind,
		MessagePredicate
	} from '$lib/message-browser/types';

	let {
		browser,
		knownPartitions,
		onDocumentChange
	}: {
		browser: MessageBrowserState;
		knownPartitions: number[];
		onDocumentChange: (document: MessageFilterDocument) => void;
	} = $props();

	const MESSAGE_MODE_OPTIONS: [MessageModeKind, string][] = [
		['newest', 'Newest'],
		['timeRange', 'Time range'],
		['offsetRange', 'Offset range']
	];
	const TIME_COLUMN_OPTIONS: [('landed' | 'kafka'), string][] = [
		['landed', 'landed at'],
		['kafka', 'broker time']
	];
	const initialMode: MessageMode = untrack(() => browser.document.mode);
	let facetPathText = $state<string>(untrack(() => browser.facetPath.join('.')));
	let previewPathText = $state<string>('');
	let fromTimeText = $state<string>(initialMode.fromTime?.replace(' ', 'T') ?? '');
	let toTimeText = $state<string>(initialMode.toTime?.replace(' ', 'T') ?? '');
	let offsetPartitionText = $state<string>(initialMode.partition == null ? '' : String(initialMode.partition));
	let fromOffsetText = $state<string>(initialMode.fromOffset == null ? '' : String(initialMode.fromOffset));
	let toOffsetText = $state<string>(initialMode.toOffset == null ? '' : String(initialMode.toOffset));
	const searchSignature = $derived(JSON.stringify({ document: browser.document, facetPath: browser.facetPath }));

	$effect(() => {
		void searchSignature;
		const timer: ReturnType<typeof setTimeout> = setTimeout(() => void browser.refresh(), 150);
		return () => clearTimeout(timer);
	});

	function applyDocument(next: MessageFilterDocument): void {
		browser.setDocument(next);
		onDocumentChange(next);
	}

	function addPredicate(predicate: MessagePredicate): void {
		applyDocument({ ...browser.document, predicates: [...browser.document.predicates, predicate] });
	}

	function removePredicate(index: number): void {
		applyDocument({
			...browser.document,
			predicates: browser.document.predicates.filter((_, at) => at !== index)
		});
	}

	function pickMode(kind: MessageModeKind): void {
		if (kind === 'newest') applyDocument({ ...browser.document, mode: { kind } });
		if (kind !== 'newest' && browser.document.mode.kind !== kind) {
			browser.setDocument({ ...browser.document, mode: { ...browser.document.mode, kind } });
		}
	}

	function localInputToTimestamp(value: string): string | null {
		if (value.trim() === '') return null;
		const padded: string = value.length === 16 ? `${value}:00` : value;
		return padded.replace('T', ' ');
	}

	function applyTimeRange(): void {
		applyDocument({
			...browser.document,
			mode: {
				kind: 'timeRange',
				fromTime: localInputToTimestamp(fromTimeText),
				toTime: localInputToTimestamp(toTimeText)
			}
		});
	}

	function applyOffsetRange(): void {
		applyDocument({
			...browser.document,
			mode: {
				kind: 'offsetRange',
				partition: Number(offsetPartitionText),
				fromOffset: fromOffsetText.trim() === '' ? null : Number(fromOffsetText),
				toOffset: toOffsetText.trim() === '' ? null : Number(toOffsetText)
			}
		});
	}

	function setLimit(limit: number): void {
		applyDocument({ ...browser.document, limit });
	}

	function parsePath(text: string): (string | number)[] {
		return text.split('.').map((segment) => segment.trim()).filter((segment) => segment !== '').map((segment) => /^\d+$/.test(segment) ? Number(segment) : segment);
	}

	function applyFacetPath(): void {
		browser.setFacetPath(parsePath(facetPathText));
	}

	function toggleFacetChip(value: string): void {
		const path: (string | number)[] = browser.facetPath;
		const existingIndex: number = browser.document.predicates.findIndex(
			(predicate) => predicate.field === 'json' && predicate.op === 'eq' && JSON.stringify(predicate.path) === JSON.stringify(path) && predicate.value === value
		);
		if (existingIndex >= 0) removePredicate(existingIndex);
		else addPredicate({ field: 'json', op: 'eq', path: [...path], value });
	}

	function addPreviewPath(): void {
		const segments: (string | number)[] = parsePath(previewPathText);
		if (segments.length === 0 || browser.document.previewPaths.length >= 4) return;
		previewPathText = '';
		applyDocument({ ...browser.document, previewPaths: [...browser.document.previewPaths, segments] });
	}

	function removePreviewPath(index: number): void {
		applyDocument({
			...browser.document,
			previewPaths: browser.document.previewPaths.filter((_, at) => at !== index)
		});
	}
</script>

<div class="flex flex-wrap items-center gap-2">
	<div class="flex overflow-hidden rounded-[4px] border border-border">
		{#each MESSAGE_MODE_OPTIONS as [kind, label] (kind)}
			<button class="px-2.5 py-1 font-mono text-[10.5px] {browser.document.mode.kind === kind ? 'bg-[var(--sb-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'} border-l border-border first:border-l-0" onclick={() => pickMode(kind)}>{label}</button>
		{/each}
	</div>

	{#if browser.document.mode.kind === 'newest'}
		<div class="flex overflow-hidden rounded-[4px] border border-border">
			{#each [50, 100, 250, 500] as limit (limit)}
				<button class="px-2 py-1 font-mono text-[10.5px] {browser.document.limit === limit ? 'bg-[var(--sb-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'} border-l border-border first:border-l-0" onclick={() => setLimit(limit)}>{limit}</button>
			{/each}
		</div>
	{:else if browser.document.mode.kind === 'timeRange'}
		<input type="datetime-local" bind:value={fromTimeText} class="bg-[var(--sb-inset)] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]" />
		<span class="text-[var(--sb-text-faint)] font-mono text-[10.5px]">→</span>
		<input type="datetime-local" bind:value={toTimeText} class="bg-[var(--sb-inset)] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]" />
		<div class="flex overflow-hidden rounded-[4px] border border-border">
			{#each TIME_COLUMN_OPTIONS as [column, label] (column)}
				<button class="px-2 py-1 font-mono text-[10px] {browser.document.timeColumn === column ? 'bg-[var(--sb-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'} border-l border-border first:border-l-0" onclick={() => applyDocument({ ...browser.document, timeColumn: column })}>{label}</button>
			{/each}
		</div>
		<button class="rounded-[4px] border border-[var(--primary)] px-2 py-1 font-mono text-[10.5px] disabled:opacity-40" disabled={fromTimeText === '' && toTimeText === ''} onclick={applyTimeRange}>apply</button>
	{:else}
		<input bind:value={offsetPartitionText} placeholder="partition" class="bg-[var(--sb-inset)] w-[90px] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]" />
		<input bind:value={fromOffsetText} placeholder="from offset" class="bg-[var(--sb-inset)] w-[110px] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]" />
		<input bind:value={toOffsetText} placeholder="to offset" class="bg-[var(--sb-inset)] w-[110px] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]" />
		<button class="rounded-[4px] border border-[var(--primary)] px-2 py-1 font-mono text-[10.5px] disabled:opacity-40" disabled={!/^\d+$/.test(offsetPartitionText.trim())} onclick={applyOffsetRange}>apply</button>
	{/if}

	<ChipEditor {knownPartitions} onAdd={addPredicate} />
	{#each browser.document.predicates as predicate, index (index)}
		<span class="bg-[var(--sb-hover)] flex items-center gap-1 rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px]">
			{predicateLabel(predicate)}
			<button class="text-muted-foreground hover:text-foreground" onclick={() => removePredicate(index)} title="remove filter"><XIcon size={10} /></button>
		</span>
	{/each}
</div>

<div class="flex flex-wrap items-center gap-2">
	<input bind:value={previewPathText} placeholder="preview field, e.g. data.placer" class="bg-[var(--sb-inset)] w-[220px] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px] outline-none focus:border-[var(--primary)]" onkeydown={(event) => { if (event.key === 'Enter') addPreviewPath(); }} />
	{#each browser.document.previewPaths as path, index (index)}
		<span class="flex items-center gap-1 rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px]">{path.join('.')}<button class="text-muted-foreground hover:text-foreground" onclick={() => removePreviewPath(index)}><XIcon size={10} /></button></span>
	{/each}
	<span class="text-[var(--sb-text-faint)] ml-auto flex items-center gap-1.5 font-mono text-[10px]">facet <input bind:value={facetPathText} aria-label="Facet path" class="bg-[var(--sb-inset)] w-[140px] rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10px] outline-none focus:border-[var(--primary)]" onkeydown={(event) => { if (event.key === 'Enter') applyFacetPath(); }} /></span>
</div>

{#if browser.facets && browser.facets.totalCount > 0}
	<div class="flex flex-wrap items-center gap-1.5">
		{#each browser.facets.values as facet (facet.value)}
			<button class="rounded-[4px] border border-border px-2 py-[2px] font-mono text-[10.5px] hover:border-[var(--primary)]" onclick={() => toggleFacetChip(facet.value)} title="toggle equality filter">{facet.value} <span class="text-[var(--sb-text-faint)]">{formatCompact(facet.count)}</span></button>
		{/each}
		{#if browser.facets.otherCount > 0}<span class="text-[var(--sb-text-faint)] font-mono text-[10px]">+{formatCompact(browser.facets.otherCount)} other</span>{/if}
		{#if browser.facets.nullCount > 0}<span class="text-[var(--sb-text-faint)] font-mono text-[10px]">{formatCompact(browser.facets.nullCount)} without {browser.facetPath.join('.')}</span>{/if}
	</div>
{/if}

{#if browser.error}
	<div class="rounded-[4px] border px-3 py-2 font-mono text-[11.5px]" style:border-color="var(--sb-danger)" style:color="var(--sb-danger)">{browser.error}</div>
{/if}
