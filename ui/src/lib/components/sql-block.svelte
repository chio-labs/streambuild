<script module lang="ts">
	/** One switchable artifact. Module-scoped so routes can import the type. */
	export type SqlArtifact = { label: string; code: string | null; note?: string };
</script>

<script lang="ts">
	import { highlightStreambuild } from '$lib/sql/highlight';

	type Props = {
		artifacts: SqlArtifact[];
		maxHeight?: string;
		/** Shown to the right of the tab bar, e.g. a file path. */
		caption?: string;
	};
	let { artifacts, maxHeight = '340px', caption }: Props = $props();

	const available = $derived(artifacts.filter((artifact) => artifact.code !== null));
	// Empty until the user picks: `active` falls back to the first available
	// artifact, so we never read a prop during initialisation.
	let activeLabel = $state<string>('');

	const active = $derived(
		available.find((artifact) => artifact.label === activeLabel) ?? available[0]
	);
	const highlighted = $derived(active ? highlightStreambuild(active.code as string) : '');
</script>

<div class="overflow-hidden rounded-[4px] border border-border">
	{#if available.length > 1 || caption}
		<div
			class="bg-[var(--sb-surface-low)] flex items-center gap-1 border-b border-border px-2 py-1.5"
		>
			{#each available as artifact (artifact.label)}
				<button
					class="rounded-[3px] px-2 py-1 font-mono text-[10.5px] transition-colors {artifact.label ===
					active?.label
						? 'bg-[var(--sb-hover)] text-foreground'
						: 'text-muted-foreground hover:text-foreground'}"
					title={artifact.note}
					onclick={() => (activeLabel = artifact.label)}
				>
					{artifact.label}
				</button>
			{/each}
			{#if caption}
				<span class="text-[var(--sb-text-faint)] ml-auto truncate font-mono text-[10px]"
					>{caption}</span
				>
			{/if}
		</div>
	{/if}
	{#if active}
		<pre
			class="bg-[var(--sb-inset)] m-0 overflow-auto p-3 font-mono text-[11.5px] leading-[1.65]"
			style:max-height={maxHeight}><code>{@html highlighted}</code></pre>
		{#if active.note}
			<div
				class="text-[var(--sb-text-faint)] border-t border-border px-3 py-1.5 font-mono text-[10px]"
			>
				{active.note}
			</div>
		{/if}
	{:else}
		<div class="text-muted-foreground p-3 text-[12px]">No SQL for this resource.</div>
	{/if}
</div>
