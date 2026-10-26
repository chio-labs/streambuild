<script lang="ts">
	import CopyIcon from '@lucide/svelte/icons/copy';
	import CheckIcon from '@lucide/svelte/icons/check';
	import { createCopyFeedbackResource } from '$lib/presentation/_resources/copy-feedback.resource';

	type Props = {
		/** The exact command the user can paste into a shell. */
		command: string;
		disabled: boolean;
	};
	let { command, disabled }: Props = $props();

	let copied = $state<boolean>(false);
	const copyFeedback = createCopyFeedbackResource(() => (copied = false));

	async function copyCommand(): Promise<void> {
		try {
			await navigator.clipboard.writeText(command);
			copied = true;
			copyFeedback.schedule();
		} catch {}
	}

	$effect(() => () => copyFeedback.stop());
</script>

<button
	class="flex shrink-0 items-center gap-1.5 rounded-[4px] border px-2.5 py-1.5 font-mono text-[11px] {copied
		? 'border-[var(--sb-success)]'
		: 'border-border text-muted-foreground hover:text-foreground'}"
	{disabled}
	onclick={copyCommand}
>
	{#if copied}
		<CheckIcon size={12} color="var(--sb-success)" /> copied
	{:else}
		<CopyIcon size={12} /> copy
	{/if}
</button>
