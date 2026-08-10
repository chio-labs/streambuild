<script lang="ts">
	import { page } from '$app/state';
	import { replaceState } from '$app/navigation';
	import { tick } from 'svelte';
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left';
	import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw';
	import XIcon from '@lucide/svelte/icons/x';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import { getProject } from '$lib/api';
	import { sourceByName } from '$lib/domain/derive';
	import { formatBytes, formatCompact, formatInteger, formatTimestamp } from '$lib/domain/format';
	import type { Project } from '$lib/domain/types';
	import ChipEditor from './chip-editor.svelte';
	import HighlightText from './highlight-text.svelte';
	import MessageDetail from './message-detail.svelte';
	import {
		encodeFilterDocument,
		getMessageBrowserState,
		predicateLabel
	} from './state.svelte';
	import type {
		MessageFilterDocument,
		MessageModeKind,
		MessagePredicate,
		MessageRow
	} from './types';

	const project: Project = getProject();
	const sourceName = $derived(page.params.name ?? '');
	const source = $derived(sourceByName(project, sourceName));

	// The load function already resolved this state and its first query; the
	// component just attaches to the per-source session instance.
	const browser = getMessageBrowserState(page.params.name ?? '');

	// Client-side sort over the loaded page, Console-style. The server always
	// pages newest-landed-first; the display defaults to the record's own
	// broker timestamp because this is a topic view — landed-at ordering is
	// one click away when the arrival gap is what matters.
	type SortKey = 'landed' | 'broker' | 'offset' | 'key';
	let sortKey = $state<SortKey>('broker');
	let sortAsc = $state(false);

	const SORT_DEFAULT_ASCENDING: Record<SortKey, boolean> = {
		landed: false,
		broker: false,
		offset: false,
		key: true
	};

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
		if (sortKey === 'broker') {
			return (a.kafkaTimestamp ?? '').localeCompare(b.kafkaTimestamp ?? '');
		}
		if (sortKey === 'key') return a.key.localeCompare(b.key);
		return a.partition - b.partition || a.offset - b.offset;
	}

	const sortedRows = $derived.by((): MessageRow[] => {
		const sorted = [...browser.rows].sort(compareRows);
		return sortAsc ? sorted : sorted.reverse();
	});

	// Console renders ten rows per page over the fetched result set; "Load
	// older" extends the set and therefore the page count.
	const PAGE_SIZES: number[] = [10, 25, 50];
	let pageSize = $state(10);
	let pageIndex = $state(0);
	const pageCount = $derived(Math.max(Math.ceil(sortedRows.length / pageSize), 1));
	const clampedPageIndex = $derived(Math.min(pageIndex, pageCount - 1));
	const displayRows = $derived(
		sortedRows.slice(clampedPageIndex * pageSize, (clampedPageIndex + 1) * pageSize)
	);

	function valueFormatLabel(row: MessageRow): string {
		const first = row.valuePreview.trimStart().charAt(0);
		return first === '{' || first === '[' ? 'JSON' : 'TEXT';
	}

	function sortIndicator(key: SortKey): string {
		if (sortKey !== key) return '';
		return sortAsc ? ' ▲' : ' ▼';
	}
	let expanded = $state<string[]>([]);
	let facetPathText = $state(browser.facetPath.join('.'));
	let previewPathText = $state('');
	// Prefill mode inputs from a shared or deep-linked document so the bar
	// reflects the filters that actually produced the visible rows.
	const initialMode = browser.document.mode;
	let fromTimeText = $state(initialMode.fromTime?.replace(' ', 'T') ?? '');
	let toTimeText = $state(initialMode.toTime?.replace(' ', 'T') ?? '');
	let offsetPartitionText = $state(
		initialMode.partition === null || initialMode.partition === undefined
			? ''
			: String(initialMode.partition)
	);
	let fromOffsetText = $state(
		initialMode.fromOffset === null || initialMode.fromOffset === undefined
			? ''
			: String(initialMode.fromOffset)
	);
	let toOffsetText = $state(
		initialMode.toOffset === null || initialMode.toOffset === undefined
			? ''
			: String(initialMode.toOffset)
	);
	let scroller = $state<HTMLElement | null>(null);

	// Console-style auto-search: any change to the effective search signature
	// re-queries after a short debounce, aborting the in-flight search. The
	// signature is read synchronously so this effect tracks exactly the filter
	// state and nothing else — refresh() itself runs outside tracking.
	const searchSignature = $derived(
		JSON.stringify({
			document: browser.document,
			facetPath: browser.facetPath
		})
	);
	$effect(() => {
		void searchSignature;
		const timer = setTimeout(() => void browser.refresh(), 150);
		return () => clearTimeout(timer);
	});
	$effect(() => {
		return () => browser.stop();
	});

	/** Every filter change flows through here: URL stays a shareable session link.
	    Expanded rows are keyed by partition:offset, so rows that survive the new
	    filter stay expanded instead of collapsing underneath the operator. */
	function applyDocument(next: MessageFilterDocument): void {
		browser.document = next;
		const encoded = encodeFilterDocument(next);
		const url = new URL(page.url);
		if (encoded === null) url.searchParams.delete('q');
		else url.searchParams.set('q', encoded);
		replaceState(url, {});
	}

	function addPredicate(predicate: MessagePredicate): void {
		applyDocument({
			...browser.document,
			predicates: [...browser.document.predicates, predicate]
		});
	}

	function removePredicate(index: number): void {
		applyDocument({
			...browser.document,
			predicates: browser.document.predicates.filter((_, at) => at !== index)
		});
	}

	function pickMode(kind: MessageModeKind): void {
		if (kind === 'newest') applyDocument({ ...browser.document, mode: { kind } });
		// timeRange and offsetRange wait for their Apply buttons; switching the
		// selector alone must not fire a query with incomplete bounds.
		if (kind !== 'newest' && browser.document.mode.kind !== kind) {
			browser.document = { ...browser.document, mode: { ...browser.document.mode, kind } };
		}
	}

	function localInputToTimestamp(value: string): string | null {
		if (value.trim() === '') return null;
		const padded = value.length === 16 ? `${value}:00` : value;
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

	function applyFacetPath(): void {
		browser.facetPath = facetPathText
			.split('.')
			.map((segment) => segment.trim())
			.filter((segment) => segment !== '')
			.map((segment) => (/^\d+$/.test(segment) ? Number(segment) : segment));
	}

	/** Facet click toggles an equality chip on the current facet path. */
	function toggleFacetChip(value: string): void {
		const path = browser.facetPath;
		const existingIndex = browser.document.predicates.findIndex(
			(predicate) =>
				predicate.field === 'json' &&
				predicate.op === 'eq' &&
				JSON.stringify(predicate.path) === JSON.stringify(path) &&
				predicate.value === value
		);
		if (existingIndex >= 0) removePredicate(existingIndex);
		else addPredicate({ field: 'json', op: 'eq', path: [...path], value });
	}

	function addPreviewPath(): void {
		const segments = previewPathText
			.split('.')
			.map((segment) => segment.trim())
			.filter((segment) => segment !== '')
			.map((segment) => (/^\d+$/.test(segment) ? Number(segment) : segment));
		if (segments.length === 0 || browser.document.previewPaths.length >= 4) return;
		previewPathText = '';
		applyDocument({
			...browser.document,
			previewPaths: [...browser.document.previewPaths, segments]
		});
	}

	function removePreviewPath(index: number): void {
		applyDocument({
			...browser.document,
			previewPaths: browser.document.previewPaths.filter((_, at) => at !== index)
		});
	}

	function rowKey(row: MessageRow): string {
		return `${row.partition}:${row.offset}`;
	}

	/** Expand/collapse keeping the clicked row visually stationary. */
	async function toggleRow(event: MouseEvent, row: MessageRow): Promise<void> {
		const rowElement = (event.currentTarget as HTMLElement).closest('tr');
		const before = rowElement?.getBoundingClientRect().top ?? 0;
		const key = rowKey(row);
		expanded = expanded.includes(key)
			? expanded.filter((candidate) => candidate !== key)
			: [...expanded, key];
		await tick();
		const after = rowElement?.getBoundingClientRect().top ?? before;
		if (scroller) scroller.scrollTop += after - before;
	}

	const columnCount = $derived(5 + browser.document.previewPaths.length);

	// Active filter criteria light up inside the cells they filtered, so the
	// table never reshapes to explain why a row matched.
	const keyHighlightTerms = $derived(
		browser.document.predicates
			.filter((predicate) => predicate.field === 'key' && typeof predicate.value === 'string')
			.map((predicate) => String(predicate.value))
	);
	const valueHighlightTerms = $derived(
		browser.document.predicates
			.filter(
				(predicate) =>
					(predicate.field === 'value' || predicate.field === 'json') &&
					typeof predicate.value === 'string'
			)
			.map((predicate) => String(predicate.value))
	);
	const windowLabel = $derived(
		browser.windowSeconds === null
			? 'entire retained table'
			: browser.windowSeconds === 3600
				? 'last hour'
				: 'last 24 hours'
	);
</script>

<AppTopbar title="{sourceName} · messages" />

<div class="min-h-0 flex-1 overflow-auto" bind:this={scroller}>
	{#if !source}
		<div class="px-[18px] py-10 text-center">
			<p class="text-muted-foreground text-[13px]">No source named <code>{sourceName}</code>.</p>
			<a href="/sources" class="text-primary mt-2 inline-block font-mono text-[11.5px]"
				>← Back to sources</a
			>
		</div>
	{:else}
		<!-- ── HEADER ─────────────────────────────────────────────────────────
		     Warehouse browsing is honest about the landing gap: broker messages
		     that have not landed yet cannot appear below. -->
		<div class="flex items-center gap-2.5 border-b border-border px-[18px] py-2.5">
			<a
				href="/sources/{sourceName}"
				class="text-muted-foreground hover:text-foreground flex items-center gap-1 font-mono text-[11px]"
				><ArrowLeftIcon size={12} /> {sourceName}</a
			>
			{#if source.topic}<span class="sb-tag code">{source.topic}</span>{/if}
			{#if source.live.kafkaLagMessages !== null && source.live.kafkaLagMessages > 0}
				<span class="font-mono text-[10.5px]" style:color="var(--sb-warning)">
					{formatCompact(source.live.kafkaLagMessages)} messages not yet landed
				</span>
			{/if}
			<button
				class="text-muted-foreground hover:text-foreground ml-auto flex items-center gap-1 rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
				onclick={() => void browser.refresh('manual')}
				><RefreshCwIcon size={11} class={browser.loading ? 'animate-spin' : ''} /> refresh</button
			>
		</div>

		<div class="flex flex-col gap-3 px-[18px] py-3">
			<!-- ── FILTER BAR ──────────────────────────────────────────────────── -->
			<div class="flex flex-wrap items-center gap-2">
				<div class="flex overflow-hidden rounded-[4px] border border-border">
					{#each [['newest', 'Newest'], ['timeRange', 'Time range'], ['offsetRange', 'Offset range']] as const as [kind, label] (kind)}
						<button
							class="px-2.5 py-1 font-mono text-[10.5px] {browser.document.mode.kind === kind
								? 'bg-[var(--sb-hover)] text-foreground'
								: 'text-muted-foreground hover:text-foreground'} border-l border-border first:border-l-0"
							onclick={() => pickMode(kind)}>{label}</button
						>
					{/each}
				</div>

				{#if browser.document.mode.kind === 'newest'}
					<div class="flex overflow-hidden rounded-[4px] border border-border">
						{#each [50, 100, 250, 500] as limit (limit)}
							<button
								class="px-2 py-1 font-mono text-[10.5px] {browser.document.limit === limit
									? 'bg-[var(--sb-hover)] text-foreground'
									: 'text-muted-foreground hover:text-foreground'} border-l border-border first:border-l-0"
								onclick={() => setLimit(limit)}>{limit}</button
							>
						{/each}
					</div>
				{:else if browser.document.mode.kind === 'timeRange'}
					<input
						type="datetime-local"
						bind:value={fromTimeText}
						class="bg-[var(--sb-inset)] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
					/>
					<span class="text-[var(--sb-text-faint)] font-mono text-[10.5px]">→</span>
					<input
						type="datetime-local"
						bind:value={toTimeText}
						class="bg-[var(--sb-inset)] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
					/>
					<div class="flex overflow-hidden rounded-[4px] border border-border">
						{#each [['landed', 'landed at'], ['kafka', 'broker time']] as const as [column, label] (column)}
							<button
								class="px-2 py-1 font-mono text-[10px] {browser.document.timeColumn === column
									? 'bg-[var(--sb-hover)] text-foreground'
									: 'text-muted-foreground hover:text-foreground'} border-l border-border first:border-l-0"
								onclick={() =>
									applyDocument({ ...browser.document, timeColumn: column })}>{label}</button
							>
						{/each}
					</div>
					<button
						class="rounded-[4px] border border-[var(--primary)] px-2 py-1 font-mono text-[10.5px] disabled:opacity-40"
						disabled={fromTimeText === '' && toTimeText === ''}
						onclick={applyTimeRange}>apply</button
					>
				{:else}
					<input
						bind:value={offsetPartitionText}
						placeholder="partition"
						class="bg-[var(--sb-inset)] w-[90px] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
					/>
					<input
						bind:value={fromOffsetText}
						placeholder="from offset"
						class="bg-[var(--sb-inset)] w-[110px] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
					/>
					<input
						bind:value={toOffsetText}
						placeholder="to offset"
						class="bg-[var(--sb-inset)] w-[110px] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
					/>
					<button
						class="rounded-[4px] border border-[var(--primary)] px-2 py-1 font-mono text-[10.5px] disabled:opacity-40"
						disabled={!/^\d+$/.test(offsetPartitionText.trim())}
						onclick={applyOffsetRange}>apply</button
					>
				{/if}

				<ChipEditor
					knownPartitions={source.live.partitions.map((partition) => partition.partition)}
					onAdd={addPredicate}
				/>

				{#each browser.document.predicates as predicate, index (index)}
					<span
						class="bg-[var(--sb-hover)] flex items-center gap-1 rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px]"
					>
						{predicateLabel(predicate)}
						<button
							class="text-muted-foreground hover:text-foreground"
							onclick={() => removePredicate(index)}
							title="remove filter"><XIcon size={10} /></button
						>
					</span>
				{/each}

			</div>

			<!-- preview fields: chosen JSON paths become list columns -->
			<div class="flex flex-wrap items-center gap-2">
				<input
					bind:value={previewPathText}
					placeholder="preview field, e.g. data.placer"
					class="bg-[var(--sb-inset)] w-[220px] rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px] outline-none focus:border-[var(--primary)]"
					onkeydown={(event) => {
						if (event.key === 'Enter') addPreviewPath();
					}}
				/>
				{#each browser.document.previewPaths as path, index (index)}
					<span
						class="flex items-center gap-1 rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px]"
					>
						{path.join('.')}
						<button
							class="text-muted-foreground hover:text-foreground"
							onclick={() => removePreviewPath(index)}><XIcon size={10} /></button
						>
					</span>
				{/each}
				<span class="text-[var(--sb-text-faint)] ml-auto flex items-center gap-1.5 font-mono text-[10px]">
					facet
					<input
						bind:value={facetPathText}
						aria-label="Facet path"
						class="bg-[var(--sb-inset)] w-[140px] rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10px] outline-none focus:border-[var(--primary)]"
						onkeydown={(event) => {
							if (event.key === 'Enter') applyFacetPath();
						}}
					/>
				</span>
			</div>

			<!-- ── FACET STRIP ────────────────────────────────────────────────── -->
			{#if browser.facets && browser.facets.totalCount > 0}
				<div class="flex flex-wrap items-center gap-1.5">
					{#each browser.facets.values as facet (facet.value)}
						<button
							class="rounded-[4px] border border-border px-2 py-[2px] font-mono text-[10.5px] hover:border-[var(--primary)]"
							onclick={() => toggleFacetChip(facet.value)}
							title="toggle equality filter"
							>{facet.value}
							<span class="text-[var(--sb-text-faint)]">{formatCompact(facet.count)}</span></button
						>
					{/each}
					{#if browser.facets.otherCount > 0}
						<span class="text-[var(--sb-text-faint)] font-mono text-[10px]"
							>+{formatCompact(browser.facets.otherCount)} other</span
						>
					{/if}
					{#if browser.facets.nullCount > 0}
						<span class="text-[var(--sb-text-faint)] font-mono text-[10px]"
							>{formatCompact(browser.facets.nullCount)} without {browser.facetPath.join('.')}</span
						>
					{/if}
				</div>
			{/if}

			{#if browser.error}
				<div
					class="rounded-[4px] border px-3 py-2 font-mono text-[11.5px]"
					style:border-color="var(--sb-danger)"
					style:color="var(--sb-danger)"
				>
					{browser.error}
				</div>
			{/if}

			<!-- ── MESSAGE TABLE ──────────────────────────────────────────────────
			     Fixed table layout: columns keep their widths across filter changes
			     and expanded payloads can never widen the page. While a re-query is
			     in flight the previous rows stay visible, dimmed, instead of the
			     whole table blanking out. -->
			<div class="overflow-hidden rounded-[4px] border border-border">
				<table class="w-full table-fixed text-left">
					<thead>
						<tr
							class="text-[var(--sb-text-faint)] border-b border-border font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							<th class="w-[150px] px-1 py-1 font-normal">
								<button
									class="hover:text-foreground w-full px-2 py-1 text-left uppercase tracking-[0.14em]"
									onclick={() => pickSort('broker')}>Timestamp{sortIndicator('broker')}</button
								>
							</th>
							<th class="w-[150px] px-1 py-1 font-normal">
								<button
									class="hover:text-foreground w-full px-2 py-1 text-left uppercase tracking-[0.14em]"
									onclick={() => pickSort('landed')}>Landed at{sortIndicator('landed')}</button
								>
							</th>
							<th class="w-[120px] px-1 py-1 font-normal">
								<button
									class="hover:text-foreground w-full px-2 py-1 text-left uppercase tracking-[0.14em]"
									onclick={() => pickSort('offset')}>P / Offset{sortIndicator('offset')}</button
								>
							</th>
							<th class="w-[200px] px-1 py-1 font-normal">
								<button
									class="hover:text-foreground w-full px-2 py-1 text-left uppercase tracking-[0.14em]"
									onclick={() => pickSort('key')}>Key{sortIndicator('key')}</button
								>
							</th>
							<th class="px-3 py-2 font-normal">Value</th>
							{#each browser.document.previewPaths as path, index (index)}
								<th class="w-[180px] px-3 py-2 font-normal normal-case">{path.join('.')}</th>
							{/each}
						</tr>
					</thead>
					<tbody class={browser.loading && browser.rows.length > 0 ? 'opacity-50' : ''}>
						{#if browser.loading && browser.rows.length === 0}
							<tr><td colspan={columnCount} class="text-muted-foreground px-3 py-6 text-center font-mono text-[11px]">querying the warehouse…</td></tr>
						{:else if !browser.loading && browser.rows.length === 0 && browser.error !== null}
							<tr><td colspan={columnCount} class="px-3 py-6 text-center font-mono text-[11px]" style:color="var(--sb-danger)">query failed — adjust the filters above</td></tr>
						{:else if !browser.loading && browser.rows.length === 0}
							<tr><td colspan={columnCount} class="text-muted-foreground px-3 py-6 text-center font-mono text-[11px]">no messages match — searched the {windowLabel}</td></tr>
						{:else}
							{#each displayRows as row (rowKey(row))}
								<tr
									class="cursor-pointer border-b border-[var(--border-subtle)] last:border-b-0 hover:bg-[var(--sb-hover)]"
									onclick={(event) => void toggleRow(event, row)}
								>
									<td class="text-muted-foreground code whitespace-nowrap px-3 py-1.5 text-[11px]"
										>{row.kafkaTimestamp === null ? '—' : formatTimestamp(row.kafkaTimestamp)}</td
									>
									<td class="text-muted-foreground code whitespace-nowrap px-3 py-1.5 text-[11px]"
										>{formatTimestamp(row.landedAt)}</td
									>
									<td class="code whitespace-nowrap px-3 py-1.5 text-[11px]"
										>{row.partition} / {formatInteger(row.offset)}</td
									>
									<td class="px-3 py-1.5">
										<div class="code truncate text-[11.5px]">
											{#if row.key}<HighlightText text={row.key} terms={keyHighlightTerms} />{:else}—{/if}
										</div>
										<div class="text-[var(--sb-text-faint)] font-mono text-[9.5px]">
											TEXT - {formatBytes(row.keyBytes)}
										</div>
									</td>
									<td class="px-3 py-1.5">
										<div class="text-muted-foreground code truncate text-[11px]">
											<HighlightText
												text={row.valuePreview}
												terms={valueHighlightTerms}
											/>{row.valueTruncated ? ' …' : ''}
										</div>
										<div class="text-[var(--sb-text-faint)] font-mono text-[9.5px]">
											{valueFormatLabel(row)} - {formatBytes(row.valueBytes)}
										</div>
									</td>
									{#each row.previewValues as previewValue, index (index)}
										<td class="text-muted-foreground code truncate px-3 py-1.5 text-[11px]"
											>{previewValue || '—'}</td
										>
									{/each}
								</tr>
								{#if expanded.includes(rowKey(row))}
									<tr class="border-b border-[var(--border-subtle)] last:border-b-0">
										<td colspan={columnCount} class="px-3 py-2">
											<MessageDetail {sourceName} {row} />
										</td>
									</tr>
								{/if}
							{/each}
						{/if}
					</tbody>
				</table>
			</div>

			<div class="flex flex-wrap items-center gap-3 pb-4">
				{#if !browser.loading && browser.rows.length > 0}
					<span class="text-[var(--sb-text-faint)] font-mono text-[10.5px]">
						{formatInteger(browser.rows.length)} messages · searched the {windowLabel}
					</span>
				{/if}
				{#if pageCount > 1}
					<div class="flex items-center gap-1">
						<button
							class="text-muted-foreground hover:text-foreground rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px] disabled:opacity-40"
							disabled={clampedPageIndex === 0}
							onclick={() => (pageIndex = clampedPageIndex - 1)}>‹</button
						>
						{#each Array.from({ length: pageCount }, (_, index) => index) as candidate (candidate)}
							<button
								class="rounded-[4px] border px-2 py-[3px] font-mono text-[10.5px] {candidate ===
								clampedPageIndex
									? 'border-[var(--primary)] text-foreground'
									: 'text-muted-foreground border-border hover:text-foreground'}"
								onclick={() => (pageIndex = candidate)}>{candidate + 1}</button
							>
						{/each}
						<button
							class="text-muted-foreground hover:text-foreground rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px] disabled:opacity-40"
							disabled={clampedPageIndex >= pageCount - 1}
							onclick={() => (pageIndex = clampedPageIndex + 1)}>›</button
						>
					</div>
				{/if}
				<div class="flex overflow-hidden rounded-[4px] border border-border">
					{#each PAGE_SIZES as candidate (candidate)}
						<button
							class="border-l border-border px-2 py-[3px] font-mono text-[10px] first:border-l-0 {pageSize ===
							candidate
								? 'bg-[var(--sb-hover)] text-foreground'
								: 'text-muted-foreground hover:text-foreground'}"
							onclick={() => {
								pageSize = candidate;
								pageIndex = 0;
							}}>{candidate} / page</button
						>
					{/each}
				</div>
				{#if browser.nextCursor !== null}
					<button
						class="text-muted-foreground hover:text-foreground rounded-[4px] border border-border px-2.5 py-1 font-mono text-[10.5px] disabled:opacity-40"
						disabled={browser.loadingOlder}
						onclick={() => void browser.loadOlder()}
						>{browser.loadingOlder ? 'loading…' : 'Load older ↓'}</button
					>
				{/if}
			</div>
		</div>
	{/if}
</div>
