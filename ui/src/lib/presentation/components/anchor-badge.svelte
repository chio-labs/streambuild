<script lang="ts">
	import AnchorIcon from '@lucide/svelte/icons/anchor';
	import { ANCHOR_REASON } from '$lib/domain/constants';
	import type { AnchorState } from '$lib/domain/types';

	type Props = { anchor: AnchorState; showReason?: boolean };
	let { anchor, showReason = false }: Props = $props();

	// Anchor eligibility is StreamBuild-native and operationally meaningful — it's
	// where a replay can start. Crucially we show WHY NOT, which the CLI never does.
	const shortLabel: Record<AnchorState, string> = {
		eligible: 'anchor',
		aggregate: 'aggregate',
		mutable_ref: 'mutable ref',
		never: 'anchor never',
		lineage_loss: 'no lineage',
		view: 'view'
	};

	const eligible = $derived(anchor === 'eligible');
</script>

<span
	class="inline-flex items-center gap-1 font-mono text-[10.5px]"
	style:color={eligible ? 'var(--sb-secondary)' : 'var(--sb-text-faint)'}
	title={ANCHOR_REASON[anchor]}
>
	{#if eligible}<AnchorIcon size={11} />{/if}
	{shortLabel[anchor]}
</span>
{#if showReason}
	<span class="text-muted-foreground text-[11px] leading-snug">{ANCHOR_REASON[anchor]}</span>
{/if}
