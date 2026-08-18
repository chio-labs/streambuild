<script lang="ts">
	import CopyIcon from '@lucide/svelte/icons/copy';
	import DownloadIcon from '@lucide/svelte/icons/download';
	import {
		capErrorText,
		formatByteSize,
		type CappedText
	} from '$lib/presentation/_helpers/error/cap';
	import { createCopyFeedbackResource } from '$lib/presentation/_resources/copy-feedback.resource';

	type Props = {
		/** The complete, uncapped error text. Copy and download use this in full. */
		text: string;
		maxHeight?: string;
		limitBytes?: number;
	};
	let { text, maxHeight = '60vh', limitBytes }: Props = $props();

	let wrap = $state(true);
	let copied = $state(false);
	const copyFeedback = createCopyFeedbackResource(() => (copied = false));

	const capped = $derived<CappedText>(capErrorText(text, limitBytes));

	async function copyFull(): Promise<void> {
		await navigator.clipboard.writeText(text);
		copied = true;
		copyFeedback.schedule();
	}

	function downloadFull(): void {
		const blob: Blob = new Blob([text], { type: 'text/plain' });
		const url: string = URL.createObjectURL(blob);
		const anchor: HTMLAnchorElement = document.createElement('a');
		anchor.href = url;
		anchor.download = 'error.txt';
		anchor.click();
		URL.revokeObjectURL(url);
	}
</script>

<div
	class="flex min-h-0 flex-col overflow-hidden rounded-[4px] border"
	style:border-color="color-mix(in srgb, var(--sb-error) 45%, var(--border))"
>
	<div class="bg-[var(--sb-surface-low)] flex items-center gap-1 border-b border-border px-2 py-1.5">
		<button
			aria-pressed={wrap}
			class="rounded-[3px] px-2 py-1 font-mono text-[10.5px] transition-colors {wrap
				? 'bg-[var(--sb-hover)] text-foreground'
				: 'text-muted-foreground hover:text-foreground'}"
			onclick={() => (wrap = !wrap)}>{wrap ? 'wrap' : 'nowrap'}</button
		>
		<button
			class="text-muted-foreground hover:text-foreground ml-auto flex items-center gap-1 rounded-[3px] px-2 py-1 font-mono text-[10px]"
			aria-label="Copy full error"
			onclick={copyFull}><CopyIcon size={11} /> {copied ? 'copied' : 'copy'}</button
		>
		<button
			class="text-muted-foreground hover:text-foreground flex items-center gap-1 rounded-[3px] px-2 py-1 font-mono text-[10px]"
			aria-label="Download full error"
			onclick={downloadFull}><DownloadIcon size={11} /> download</button
		>
	</div>
	<pre
		class="text-foreground m-0 min-h-0 flex-1 overflow-auto bg-[var(--sb-inset)] p-3 font-mono text-[11.5px] leading-[1.6] {wrap
			? 'whitespace-pre-wrap'
			: 'whitespace-pre'}"
		style:max-height={maxHeight}>{capped.text}</pre>
	{#if capped.isTruncated}
		<div
			class="border-t border-border px-3 py-1.5 font-mono text-[10px]"
			style:color="var(--sb-warning)"
		>
			Display capped — {formatByteSize(capped.truncatedBytes)} hidden. Use copy or download for the
			complete error.
		</div>
	{/if}
</div>
