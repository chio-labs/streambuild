<script lang="ts">
	import { tick } from 'svelte';
	import { formatBytes } from '$lib/formatting/main/format-bytes';
	import { formatInteger } from '$lib/formatting/main/format-integer';
	import { formatTimestamp } from '$lib/formatting/main/format-timestamp';
	import HighlightText from '$lib/message-browser/components/highlight-text.svelte';
	import MessageDetail from '$lib/message-browser/components/message-detail.svelte';
	import type { MessageBrowserState, MessageRow } from '$lib/message-browser/types';

	let { browser, sourceName }: { browser: MessageBrowserState; sourceName: string } = $props();

	type SortKey = 'landed' | 'broker' | 'offset' | 'key';
	const SORT_DEFAULT_ASCENDING: Record<SortKey, boolean> = { landed: false, broker: false, offset: false, key: true };
	const PAGE_SIZES: number[] = [10, 25, 50];
	let sortKey = $state<SortKey>('broker');
	let sortAsc = $state<boolean>(false);
	let pageSize = $state<number>(10);
	let pageIndex = $state<number>(0);
	let expanded = $state<string[]>([]);

	function pickSort(key: SortKey): void {
		if (sortKey === key) {
			sortAsc = !sortAsc;
			return;
		}
		sortKey = key;
		sortAsc = SORT_DEFAULT_ASCENDING[key];
	}

	function compareRows(a: MessageRow, b: MessageRow): number {
		if (sortKey === 'landed') return a.landedAt.localeCompare(b.landedAt);
		if (sortKey === 'broker') return (a.kafkaTimestamp ?? '').localeCompare(b.kafkaTimestamp ?? '');
		if (sortKey === 'key') return a.key.localeCompare(b.key);
		return a.partition - b.partition || a.offset - b.offset;
	}

	const sortedRows = $derived.by((): MessageRow[] => {
		const sorted: MessageRow[] = [...browser.rows].sort(compareRows);
		return sortAsc ? sorted : sorted.reverse();
	});
	const pageCount = $derived(Math.max(Math.ceil(sortedRows.length / pageSize), 1));
	const clampedPageIndex = $derived(Math.min(pageIndex, pageCount - 1));
	const displayRows = $derived(sortedRows.slice(clampedPageIndex * pageSize, (clampedPageIndex + 1) * pageSize));
	const columnCount = $derived(5 + browser.document.previewPaths.length);
	const keyHighlightTerms = $derived(browser.document.predicates.filter((predicate) => predicate.field === 'key' && typeof predicate.value === 'string').map((predicate) => String(predicate.value)));
	const valueHighlightTerms = $derived(browser.document.predicates.filter((predicate) => (predicate.field === 'value' || predicate.field === 'json') && typeof predicate.value === 'string').map((predicate) => String(predicate.value)));
	const windowLabel = $derived(browser.windowSeconds === null ? 'entire retained table' : browser.windowSeconds === 3600 ? 'last hour' : 'last 24 hours');

	function valueFormatLabel(row: MessageRow): string {
		const first: string = row.valuePreview.trimStart().charAt(0);
		return first === '{' || first === '[' ? 'JSON' : 'TEXT';
	}

	function sortIndicator(key: SortKey): string {
		if (sortKey !== key) return '';
		return sortAsc ? ' ▲' : ' ▼';
	}

	function rowKey(row: MessageRow): string {
		return `${row.partition}:${row.offset}`;
	}

	async function toggleRow(event: MouseEvent, row: MessageRow): Promise<void> {
		const rowElement: HTMLTableRowElement | null = (event.currentTarget as HTMLElement).closest('tr');
		const scroller: HTMLElement | null = rowElement?.closest('.message-scroller') ?? null;
		const before: number = rowElement?.getBoundingClientRect().top ?? 0;
		const key: string = rowKey(row);
		expanded = expanded.includes(key) ? expanded.filter((candidate) => candidate !== key) : [...expanded, key];
		await tick();
		const after: number = rowElement?.getBoundingClientRect().top ?? before;
		if (scroller) scroller.scrollTop += after - before;
	}
</script>

<div class="overflow-hidden rounded-[4px] border border-border">
	<table class="w-full table-fixed text-left">
		<thead><tr class="text-[var(--sb-text-faint)] border-b border-border font-mono text-[10px] uppercase tracking-[0.14em]">
			<th class="w-[150px] px-1 py-1 font-normal"><button class="hover:text-foreground w-full px-2 py-1 text-left uppercase tracking-[0.14em]" onclick={() => pickSort('broker')}>Timestamp{sortIndicator('broker')}</button></th>
			<th class="w-[150px] px-1 py-1 font-normal"><button class="hover:text-foreground w-full px-2 py-1 text-left uppercase tracking-[0.14em]" onclick={() => pickSort('landed')}>Landed at{sortIndicator('landed')}</button></th>
			<th class="w-[120px] px-1 py-1 font-normal"><button class="hover:text-foreground w-full px-2 py-1 text-left uppercase tracking-[0.14em]" onclick={() => pickSort('offset')}>P / Offset{sortIndicator('offset')}</button></th>
			<th class="w-[200px] px-1 py-1 font-normal"><button class="hover:text-foreground w-full px-2 py-1 text-left uppercase tracking-[0.14em]" onclick={() => pickSort('key')}>Key{sortIndicator('key')}</button></th>
			<th class="px-3 py-2 font-normal">Value</th>
			{#each browser.document.previewPaths as path, index (index)}<th class="w-[180px] px-3 py-2 font-normal normal-case">{path.join('.')}</th>{/each}
		</tr></thead>
		<tbody class={browser.loading && browser.rows.length > 0 ? 'opacity-50' : ''}>
			{#if browser.loading && browser.rows.length === 0}
				<tr><td colspan={columnCount} class="text-muted-foreground px-3 py-6 text-center font-mono text-[11px]">querying the warehouse…</td></tr>
			{:else if !browser.loading && browser.rows.length === 0 && browser.error !== null}
				<tr><td colspan={columnCount} class="px-3 py-6 text-center font-mono text-[11px]" style:color="var(--sb-danger)">query failed — adjust the filters above</td></tr>
			{:else if !browser.loading && browser.rows.length === 0}
				<tr><td colspan={columnCount} class="text-muted-foreground px-3 py-6 text-center font-mono text-[11px]">no messages match — searched the {windowLabel}</td></tr>
			{:else}
				{#each displayRows as row (rowKey(row))}
					<tr class="cursor-pointer border-b border-[var(--border-subtle)] last:border-b-0 hover:bg-[var(--sb-hover)]" onclick={(event) => void toggleRow(event, row)}>
						<td class="text-muted-foreground code whitespace-nowrap px-3 py-1.5 text-[11px]">{row.kafkaTimestamp === null ? '—' : formatTimestamp(row.kafkaTimestamp)}</td>
						<td class="text-muted-foreground code whitespace-nowrap px-3 py-1.5 text-[11px]">{formatTimestamp(row.landedAt)}</td>
						<td class="code whitespace-nowrap px-3 py-1.5 text-[11px]">{row.partition} / {formatInteger(row.offset)}</td>
						<td class="px-3 py-1.5"><div class="code truncate text-[11.5px]">{#if row.key}<HighlightText text={row.key} terms={keyHighlightTerms} />{:else}—{/if}</div><div class="text-[var(--sb-text-faint)] font-mono text-[9.5px]">TEXT - {formatBytes(row.keyBytes)}</div></td>
						<td class="px-3 py-1.5"><div class="text-muted-foreground code truncate text-[11px]"><HighlightText text={row.valuePreview} terms={valueHighlightTerms} />{row.valueTruncated ? ' …' : ''}</div><div class="text-[var(--sb-text-faint)] font-mono text-[9.5px]">{valueFormatLabel(row)} - {formatBytes(row.valueBytes)}</div></td>
						{#each row.previewValues as previewValue, index (index)}<td class="text-muted-foreground code truncate px-3 py-1.5 text-[11px]">{previewValue || '—'}</td>{/each}
					</tr>
					{#if expanded.includes(rowKey(row))}<tr class="border-b border-[var(--border-subtle)] last:border-b-0"><td colspan={columnCount} class="px-3 py-2"><MessageDetail {sourceName} {row} /></td></tr>{/if}
				{/each}
			{/if}
		</tbody>
	</table>
</div>

<div class="flex flex-wrap items-center gap-3 pb-4">
	{#if !browser.loading && browser.rows.length > 0}<span class="text-[var(--sb-text-faint)] font-mono text-[10.5px]">{formatInteger(browser.rows.length)} messages · searched the {windowLabel}</span>{/if}
	{#if pageCount > 1}
		<div class="flex items-center gap-1">
			<button class="text-muted-foreground hover:text-foreground rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px] disabled:opacity-40" disabled={clampedPageIndex === 0} onclick={() => (pageIndex = clampedPageIndex - 1)}>‹</button>
			{#each Array.from({ length: pageCount }, (_, index) => index) as candidate (candidate)}<button class="rounded-[4px] border px-2 py-[3px] font-mono text-[10.5px] {candidate === clampedPageIndex ? 'border-[var(--primary)] text-foreground' : 'text-muted-foreground border-border hover:text-foreground'}" onclick={() => (pageIndex = candidate)}>{candidate + 1}</button>{/each}
			<button class="text-muted-foreground hover:text-foreground rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px] disabled:opacity-40" disabled={clampedPageIndex >= pageCount - 1} onclick={() => (pageIndex = clampedPageIndex + 1)}>›</button>
		</div>
	{/if}
	<div class="flex overflow-hidden rounded-[4px] border border-border">{#each PAGE_SIZES as candidate (candidate)}<button class="border-l border-border px-2 py-[3px] font-mono text-[10px] first:border-l-0 {pageSize === candidate ? 'bg-[var(--sb-hover)] text-foreground' : 'text-muted-foreground hover:text-foreground'}" onclick={() => { pageSize = candidate; pageIndex = 0; }}>{candidate} / page</button>{/each}</div>
	{#if browser.nextCursor !== null}<button class="text-muted-foreground hover:text-foreground rounded-[4px] border border-border px-2.5 py-1 font-mono text-[10.5px] disabled:opacity-40" disabled={browser.loadingOlder} onclick={() => void browser.loadOlder()}>{browser.loadingOlder ? 'loading…' : 'Load older ↓'}</button>{/if}
</div>
