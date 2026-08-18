<script lang="ts">
	import ErrorDialog from './error-dialog.svelte';

	type Props = {
		text: string;
		title?: string;
		subtitle?: string;
		/** Extra classes for the preview button (width, spacing). */
		class?: string;
		/** Tailwind line-clamp utility for the inline preview. */
		clamp?: string;
	};
	let {
		text,
		title,
		subtitle,
		class: className = '',
		clamp = 'line-clamp-2'
	}: Props = $props();

	let open = $state(false);
</script>

<button
	type="button"
	class="block text-left {className}"
	title="View full error"
	onclick={() => (open = true)}
>
	<span
		class="{clamp} font-mono text-[10.5px] leading-snug hover:underline"
		style:color="var(--sb-error)">{text}</span
	>
</button>

<ErrorDialog bind:open {text} {title} {subtitle} />
