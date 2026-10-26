<script lang="ts">
	import { parseUnifiedDiff } from '$lib/presentation/main/_parse-unified-diff';
	import type { UnifiedDiff } from '$lib/presentation/types';

	type Props = {
		/** Unified diff text rendered by the server, previous → current. */
		diff: string | null | undefined;
		maxHeight?: string;
	};
	let { diff, maxHeight = '14rem' }: Props = $props();

	const parsed: UnifiedDiff = $derived(parseUnifiedDiff(diff));
</script>

<div class="sql-diff overflow-hidden rounded-[3px] border border-border" data-testid="sql-diff">
	<div
		class="bg-[var(--sb-surface-low)] flex items-center gap-2 border-b border-border px-2 py-1 font-mono text-[10px]"
	>
		<span class="text-[var(--sb-text-faint)]">previous → current</span>
		<span class="ml-auto flex gap-2 font-semibold" aria-label="Changed lines">
			<span class="stat-add">+{parsed.added}</span>
			<span class="stat-del">−{parsed.removed}</span>
		</span>
	</div>
	<div
		class="bg-[var(--sb-inset)] overflow-auto py-1 font-mono text-[10.5px] leading-relaxed"
		style:max-height={maxHeight}
	>
		{#each parsed.lines as line, index (index)}
			<div class="diff-line {line.kind}" data-diff-kind={line.kind}>
				<span class="sign" aria-hidden="true">{line.sign}</span><code>{line.text}</code>
			</div>
		{/each}
	</div>
</div>

<style>
	.diff-line {
		display: flex;
		min-width: max-content;
		padding-right: 12px;
	}
	.diff-line code {
		font: inherit;
		white-space: pre;
	}
	.sign {
		flex: 0 0 18px;
		width: 18px;
		text-align: center;
		color: var(--sb-text-faint);
		user-select: none;
	}
	.diff-line.add {
		background: color-mix(in srgb, var(--sb-success) 13%, transparent);
		color: color-mix(in srgb, var(--sb-success) 55%, var(--foreground));
	}
	.diff-line.add .sign,
	.stat-add {
		color: var(--sb-success);
	}
	.diff-line.del {
		background: color-mix(in srgb, var(--sb-error) 12%, transparent);
		color: color-mix(in srgb, var(--sb-error) 55%, var(--foreground));
	}
	.diff-line.del .sign,
	.stat-del {
		color: var(--sb-error);
	}
	.diff-line.hunk {
		color: var(--primary);
		opacity: 0.85;
	}
	.diff-line.header {
		color: var(--sb-text-faint);
		opacity: 0.7;
	}
</style>
