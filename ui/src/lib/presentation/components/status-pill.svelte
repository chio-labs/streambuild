<script lang="ts">
	import type { ModelStatus } from '$lib/domain/types';

	type Props = { status: ModelStatus; compact?: boolean };
	let { status, compact = false }: Props = $props();

	// Freshness owns the alert hues. `drift` is purple because it is a
	// code-vs-baseline mismatch, not a data problem — a different class of thing.
	const config: Record<ModelStatus, { label: string; colour: string; title: string }> = {
		fresh: {
			label: 'fresh',
			colour: 'var(--sb-success)',
			title: 'Keeping up with its source'
		},
		lagging: {
			label: 'lagging',
			colour: 'var(--sb-warning)',
			title: 'Behind its source but still moving'
		},
		stalled: {
			label: 'stalled',
			colour: 'var(--sb-error)',
			title: 'No new rows for an extended period'
		},
		drift: {
			label: 'drift',
			colour: 'var(--sb-stale)',
			title: 'Definition changed since the last applied build — a rebuild is needed'
		},
		unknown: {
			label: 'unknown',
			colour: 'var(--sb-text-faint)',
			title: 'No freshness policy is configured'
		},
		source: { label: 'source', colour: 'var(--sb-text-faint)', title: 'Stream source' }
	};

	const entry = $derived(config[status]);
</script>

<span
	class="inline-flex items-center gap-1.5 font-mono text-[11px] {compact ? '' : 'whitespace-nowrap'}"
	style:color={entry.colour}
	title={entry.title}
>
	<span class="h-1.5 w-1.5 rounded-[2px]" style:background={entry.colour}></span>
	{entry.label}
</span>
