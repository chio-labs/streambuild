<script lang="ts">
	type Props = {
		label: string;
		value: string;
		/** Render the value in monospace — for relation names, expressions, modes. */
		mono?: boolean;
		tone?: 'default' | 'success' | 'warning' | 'error' | 'faint';
		href?: string;
		title?: string;
	};
	let { label, value, mono = false, tone = 'default', href, title }: Props = $props();

	const colour: Record<string, string> = {
		default: 'var(--foreground)',
		success: 'var(--sb-success)',
		warning: 'var(--sb-warning)',
		error: 'var(--sb-error)',
		faint: 'var(--sb-text-faint)'
	};
</script>

<div class="flex items-baseline gap-3 border-b border-[var(--border-subtle)] py-[7px]" {title}>
	<span class="text-muted-foreground shrink-0 text-[12px]">{label}</span>
	{#if href}
		<a
			class="text-primary ml-auto truncate text-right text-[12px] hover:underline {mono
				? 'font-mono text-[11.5px]'
				: ''}"
			{href}>{value}</a
		>
	{:else}
		<span
			class="ml-auto truncate text-right text-[12px] {mono ? 'font-mono text-[11.5px]' : ''}"
			style:color={colour[tone]}>{value}</span
		>
	{/if}
</div>
