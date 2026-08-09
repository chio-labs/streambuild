<script lang="ts">
	import CopyIcon from '@lucide/svelte/icons/copy';
	import DownloadIcon from '@lucide/svelte/icons/download';
	import { formatInteger, formatTimestamp } from '$lib/domain/format';
	import JsonBlock from './json-block.svelte';
	import { fetchMessageRecord } from './api';
	import type { MessageRecord, MessageRow } from './types';

	let { sourceName, row }: { sourceName: string; row: MessageRow } = $props();

	type DetailTab = 'key' | 'value' | 'headers';
	let tab = $state<DetailTab>('value');
	let showRaw = $state(false);
	let record = $state<MessageRecord | null>(null);
	let recordError = $state<string | null>(null);
	let copied = $state(false);

	// The list carries a truncated preview; the accordion always fetches the
	// full record by primary key so Copy/Download act on complete bytes.
	$effect(() => {
		let cancelled = false;
		record = null;
		recordError = null;
		showRaw = false;
		fetchMessageRecord(sourceName, row.partition, row.offset)
			.then((payload) => {
				if (!cancelled) record = payload;
			})
			.catch((caught) => {
				if (!cancelled) recordError = String(caught instanceof Error ? caught.message : caught);
			});
		return () => {
			cancelled = true;
		};
	});

	const recordLoading = $derived(record === null && recordError === null);
	const value = $derived(record?.value ?? row.valuePreview);
	const headers = $derived(record?.headers ?? row.headers);
	// Multi-MiB payloads render as plain text: parsing is cheap but syntax
	// highlighting megabytes of tokens would freeze the tab.
	const PRETTY_LIMIT_BYTES = 2_097_152;
	const prettyValue = $derived.by((): string | undefined => {
		if (value.length > PRETTY_LIMIT_BYTES) return undefined;
		try {
			return JSON.stringify(JSON.parse(value), null, 2);
		} catch {
			return undefined;
		}
	});

	async function copyValue(): Promise<void> {
		await navigator.clipboard.writeText(value);
		copied = true;
		setTimeout(() => (copied = false), 1200);
	}

	function downloadRecord(): void {
		const payload = {
			topic: record?.topic ?? null,
			partition: row.partition,
			offset: row.offset,
			landedAt: row.landedAt,
			kafkaTimestamp: row.kafkaTimestamp,
			key: record?.key ?? row.key,
			value,
			headers
		};
		const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const anchor = document.createElement('a');
		anchor.href = url;
		anchor.download = `${sourceName}-p${row.partition}-o${row.offset}.json`;
		anchor.click();
		URL.revokeObjectURL(url);
	}
</script>

<div class="bg-[var(--sb-inset)] rounded-[4px] border border-border p-3">
	<!-- metadata strip: the durable coordinates and sizes of this exact record -->
	<div class="text-muted-foreground flex flex-wrap items-baseline gap-x-4 gap-y-1 pb-2 font-mono text-[10.5px]">
		<span>partition <span class="text-foreground">{row.partition}</span></span>
		<span>offset <span class="text-foreground">{formatInteger(row.offset)}</span></span>
		<span>key <span class="text-foreground">{formatInteger(row.keyBytes)} B</span></span>
		<span>value <span class="text-foreground">{formatInteger(record?.valueBytes ?? row.valueBytes)} B</span></span>
		<span>landed <span class="text-foreground">{formatTimestamp(row.landedAt)}</span></span>
		<span>broker <span class="text-foreground">{row.kafkaTimestamp === null ? '—' : formatTimestamp(row.kafkaTimestamp)}</span></span>
		<span class="ml-auto flex items-center gap-1.5">
			<button
				class="text-muted-foreground hover:text-foreground flex items-center gap-1 rounded-[4px] border border-border px-2 py-0.5 disabled:opacity-50"
				disabled={recordLoading}
				onclick={copyValue}><CopyIcon size={11} /> {copied ? 'copied' : 'Copy value'}</button
			>
			<button
				class="text-muted-foreground hover:text-foreground flex items-center gap-1 rounded-[4px] border border-border px-2 py-0.5 disabled:opacity-50"
				disabled={recordLoading}
				onclick={downloadRecord}><DownloadIcon size={11} /> Download record</button
			>
		</span>
	</div>

	<div class="flex items-center gap-1 border-b border-border pb-0">
		{#each ['key', 'value', 'headers'] as const as candidate (candidate)}
			<button
				class="rounded-t-[4px] px-2.5 py-1 font-mono text-[10.5px] capitalize {tab === candidate
					? 'bg-[var(--sb-hover)] text-foreground border border-b-0 border-border'
					: 'text-muted-foreground hover:text-foreground'}"
				onclick={() => (tab = candidate)}
				>{candidate}{candidate === 'headers' ? ` (${headers.length})` : ''}</button
			>
		{/each}
		{#if tab === 'value' && prettyValue !== undefined}
			<button
				class="text-muted-foreground hover:text-foreground ml-auto px-2 py-1 font-mono text-[10px]"
				onclick={() => (showRaw = !showRaw)}>{showRaw ? 'pretty' : 'raw'}</button
			>
		{/if}
	</div>

	<div class="bg-background mt-2.5 min-h-[180px] max-h-[480px] overflow-auto rounded-[4px] border border-[var(--border-subtle)] p-2.5">
		{#if recordLoading}
			<div class="text-muted-foreground grid h-[158px] place-items-center font-mono text-[11px]">
				loading full record…
			</div>
		{:else}
		{#if recordError}
			<p class="pb-2 font-mono text-[11px]" style:color="var(--sb-danger)">
				full record unavailable — showing the truncated preview · {recordError}
			</p>
		{/if}
		{#if tab === 'key'}
			<pre class="whitespace-pre-wrap break-all font-mono text-[11.5px]">{record?.key ?? row.key}</pre>
		{:else if tab === 'value'}
			{#if prettyValue !== undefined && !showRaw}
				<JsonBlock text={prettyValue} />
			{:else}
				<pre class="whitespace-pre-wrap break-all font-mono text-[11.5px]">{value}</pre>
			{/if}
			{#if value.length > PRETTY_LIMIT_BYTES}
				<p class="pt-2 font-mono text-[10.5px]" style:color="var(--sb-warning)">
					large payload — rendered as plain text; Copy and Download carry the full bytes
				</p>
			{/if}
			{#if record?.valueTruncated}
				<p class="pt-2 font-mono text-[10.5px]" style:color="var(--sb-warning)">
					value exceeds 16 MiB — display truncated; Download record carries the same cap
				</p>
			{/if}
		{:else}
			{#if headers.length === 0}
				<p class="text-muted-foreground font-mono text-[11px]">no headers on this message</p>
			{:else}
				<table class="w-full text-left">
					<tbody>
						{#each headers as [headerKey, headerValue], index (index)}
							<tr class="border-b border-[var(--border-subtle)] last:border-b-0">
								<td class="code w-[220px] py-1 pr-3 text-[11.5px]">{headerKey}</td>
								<td class="text-muted-foreground code break-all py-1 text-[11.5px]">{headerValue}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		{/if}
		{/if}
	</div>
</div>
