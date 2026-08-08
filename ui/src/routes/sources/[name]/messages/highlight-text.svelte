<script lang="ts">
	import { splitByTerms } from './highlight';

	let { text, terms }: { text: string; terms: string[] } = $props();
	const segments = $derived(splitByTerms(text, terms));
</script>

{#each segments as segment, index (index)}{#if segment.hit}<mark
			class="rounded-[2px] bg-[var(--primary)]/25 text-inherit">{segment.text}</mark
		>{:else}{segment.text}{/if}{/each}
