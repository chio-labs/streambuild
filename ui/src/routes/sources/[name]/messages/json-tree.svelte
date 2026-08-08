<script lang="ts">
	import JsonTree from './json-tree.svelte';

	let {
		value,
		label = null,
		depth = 0
	}: { value: unknown; label?: string | null; depth?: number } = $props();

	const isComposite = $derived(typeof value === 'object' && value !== null);
	const entries = $derived.by((): [string, unknown][] => {
		if (Array.isArray(value)) return value.map((item, index) => [String(index), item]);
		if (typeof value === 'object' && value !== null) {
			return Object.entries(value as Record<string, unknown>);
		}
		return [];
	});
	const preview = $derived(
		Array.isArray(value) ? `[${entries.length}]` : `{${entries.length}}`
	);

	// Default expansion depth mirrors Redpanda Console's JSON viewer. The
	// initial-value capture is deliberate: nodes never move between depths.
	// svelte-ignore state_referenced_locally
	let open = $state(depth < 2);

	function scalarColour(scalar: unknown): string {
		if (typeof scalar === 'string') return 'var(--sb-success)';
		if (typeof scalar === 'number') return 'var(--primary)';
		if (typeof scalar === 'boolean') return 'var(--sb-warning)';
		return 'var(--sb-text-faint)';
	}

	function scalarText(scalar: unknown): string {
		if (typeof scalar === 'string') return JSON.stringify(scalar);
		return String(scalar);
	}
</script>

{#if isComposite}
	<div class="font-mono text-[11.5px] leading-[1.7]">
		<button
			class="text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
			onclick={() => (open = !open)}
		>
			<span class="text-[var(--sb-text-faint)] inline-block w-2.5">{open ? '▾' : '▸'}</span>
			{#if label !== null}<span class="text-foreground">{label}:</span>{/if}
			<span class="text-[var(--sb-text-faint)]">{preview}</span>
		</button>
		{#if open}
			<div class="border-l border-[var(--border-subtle)] ml-[4px] pl-3.5">
				{#each entries as [childLabel, childValue] (childLabel)}
					<JsonTree value={childValue} label={childLabel} depth={depth + 1} />
				{/each}
			</div>
		{/if}
	</div>
{:else}
	<div class="font-mono text-[11.5px] leading-[1.7]">
		{#if label !== null}<span class="text-foreground">{label}:</span>{/if}
		<span style:color={scalarColour(value)}>{scalarText(value)}</span>
	</div>
{/if}
