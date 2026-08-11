<script lang="ts">
	import Prism from 'prismjs';
	import 'prismjs/components/prism-json';

	let { text }: { text: string } = $props();
	const lines = $derived(Prism.highlight(text, Prism.languages.json, 'json').split('\n'));
</script>

<div class="flex min-w-0 font-mono text-[11.5px] leading-[1.65]">
	<div class="text-[var(--sb-text-faint)] bg-background sticky left-0 shrink-0 select-none border-r border-[var(--border-subtle)] pr-2.5 text-right">
		{#each lines as _line, index (index)}<div>{index + 1}</div>{/each}
	</div>
	<pre class="m-0 min-w-0 flex-1 whitespace-pre pl-3"><code
			>{#each lines as line, index (index)}<div class="min-h-[1.65em]">{@html line}</div>{/each}</code
		></pre>
</div>
