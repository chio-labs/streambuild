<script lang="ts">
	import { Handle, Position, type NodeProps } from '@xyflow/svelte';
	import RadioIcon from '@lucide/svelte/icons/radio';
	import DatabaseIcon from '@lucide/svelte/icons/database';
	import Table2Icon from '@lucide/svelte/icons/table-2';
	import EyeIcon from '@lucide/svelte/icons/eye';
	import WavesIcon from '@lucide/svelte/icons/waves';
	import AnchorIcon from '@lucide/svelte/icons/anchor';
	import GitCompareIcon from '@lucide/svelte/icons/git-compare';
	import type { Icon as IconType } from '@lucide/svelte';
	import { getNodeFields } from '$lib/lineage/main/get-node-fields';
	import { ANCHOR_REASON } from '$lib/domain/constants';
	import type { GraphNode } from '$lib/lineage/types';
	import { formatCompact } from '$lib/formatting/main/format-compact';
	import { formatRate } from '$lib/formatting/main/format-rate';

	const nodeFields = getNodeFields();

	let { data, selected }: NodeProps = $props();
	const node = $derived(data as unknown as GraphNode);
	/** Physical mode packs many more objects in, so it renders a tighter card. */
	const compact = $derived(Boolean((data as unknown as { compact?: boolean }).compact));
	const lightweight = $derived(Boolean((data as unknown as { lightweight?: boolean }).lightweight));
	/**
	 * Present but not acted on — e.g. a source the Plan page reads without
	 * rebuilding. Held back rather than hidden, because removing it would leave
	 * the closure looking self-rooting.
	 */
	const muted = $derived(Boolean((data as unknown as { muted?: boolean }).muted));
	/**
	 * Directly asked for, as opposed to pulled in by consequence — e.g. the
	 * models a Plan selector names, versus the downstream closure it drags along.
	 */
	const emphasis = $derived(Boolean((data as unknown as { emphasis?: boolean }).emphasis));
	/**
	 * A short fact that belongs to this node in the current context but is not a
	 * property of the model itself — e.g. how a Plan will bound its replay.
	 * Positioned absolutely so adding one never changes the node's measured
	 * height, which the graph layout assumes is fixed.
	 */
	const note = $derived(
		(data as unknown as { note?: { text: string; tone: 'info' | 'warn' } }).note
	);
	const fields = $derived(nodeFields.value);
	const showKind = $derived(fields.kind && (!compact || node.logicalType === 'source'));

	// AXIS 1 — status owns every alert hue. Nothing else uses these.
	const statusColour: Record<string, string> = {
		fresh: 'var(--sb-success)',
		lagging: 'var(--sb-warning)',
		stalled: 'var(--sb-error)',
		drift: 'var(--sb-stale)',
		unknown: 'var(--sb-text-faint)',
		source: 'var(--sb-text-faint)'
	};

	/**
	 * AXIS 2 — kind, in a COOL palette only, so badge colour never fakes an alert.
	 * StreamBuild's families:
	 *   slate      raw ingest + landing storage (kafka engine, raw/adopted tables)
	 *   teal-blue  materialized views — the continuously moving parts
	 *   blue       model tables
	 *   sky        terminal views
	 */
	const SLATE = '#7c8aa5';
	const TEAL = '#3fb6c9';
	const BLUE = '#2e90ff';
	const SKY = '#5aa9e6';

	type KindVisual = { colour: string; glyph: typeof IconType };

	const kindVisual = $derived.by((): KindVisual => {
		switch (node.physicalType) {
			case 'kafka_engine':
				return { colour: SLATE, glyph: RadioIcon };
			case 'landing_table':
			case 'adopted_table':
				return { colour: SLATE, glyph: DatabaseIcon };
			case 'landing_mv':
			case 'model_mv':
				return { colour: TEAL, glyph: WavesIcon };
			case 'model_table':
				return { colour: BLUE, glyph: Table2Icon };
			case 'model_view':
				return { colour: SKY, glyph: EyeIcon };
			default:
				break;
		}
		// Logical mode
		if (node.logicalType === 'source') {
			return { colour: SLATE, glyph: node.kindLabel.startsWith('KAFKA') ? RadioIcon : DatabaseIcon };
		}
		if (node.logicalType === 'view') return { colour: SKY, glyph: EyeIcon };
		return { colour: BLUE, glyph: Table2Icon };
	});

	const Glyph = $derived(kindVisual.glyph);
	const railColour = $derived(statusColour[node.status] ?? 'var(--sb-text-faint)');

	const checkColour = $derived(
		node.failingChecks > 0
			? 'var(--sb-error)'
			: node.warningChecks > 0
				? 'var(--sb-warning)'
				: 'var(--sb-success)'
	);

	// Deployment relations carry their own hue: the question they answer is
	// "is this live, waiting, or dead weight", not how fresh the model is.
	const DEPLOYMENT_COLOUR: Record<string, string> = {
		active: 'var(--sb-success)',
		staged: 'var(--sb-warning)',
		orphaned: 'var(--sb-text-faint)'
	};
	const deploymentColour = $derived(
		node.deployment ? (DEPLOYMENT_COLOUR[node.deployment.state] ?? null) : null
	);

	const showAnchor = $derived(fields.anchor && node.anchor !== null && node.anchor !== 'view');
	const showChecks = $derived(fields.checks && node.totalChecks > 0);
	const showRows = $derived(fields.rows && node.rows !== null);
	const showRate = $derived(fields.rate && node.rowsPerSecond !== null);
	const showRelation = $derived(!compact && fields.relation && node.sublabel !== null);

	const hasDetail = $derived(
		showAnchor || showChecks || showRows || showRate || node.drift || note !== undefined
	);
</script>

<div
	class="bg-card relative overflow-hidden rounded-lg border transition-opacity {muted
		? 'opacity-45 border-dashed'
		: ''} {emphasis
		? 'ring-primary/70 ring-2'
		: ''} {compact
		? 'w-[186px] px-2 py-1.5 pl-[13px]'
		: 'w-[248px] px-3 py-2.5 pl-[15px]'} {selected
		? 'border-primary'
		: 'border-[var(--border-strong)]'}"
	style:box-shadow={lightweight
		? 'none'
		: selected
			? 'var(--sb-node-shadow-selected)'
			: 'var(--sb-node-shadow)'}
>
	<!-- left rail = STATUS -->
	<span
		class="absolute bottom-0 left-0 top-0 w-[3px]"
		style:background={deploymentColour ?? (fields.status ? railColour : 'transparent')}
	></span>
	<Handle type="target" position={Position.Left} class="!border-border !bg-muted !h-2 !w-2" />

	<div class="flex items-center gap-2.5">
		<!-- icon badge = KIND (cool palette only) -->
		<span
			class="grid shrink-0 place-items-center rounded-md {compact ? 'h-5 w-5' : 'h-7 w-7'}"
			style:background="color-mix(in srgb, {kindVisual.colour} 16%, transparent)"
			style:color={kindVisual.colour}
		>
			<Glyph size={compact ? 12 : 15} strokeWidth={2} />
		</span>
		<div class="min-w-0 flex-1">
			<div
				class="truncate font-mono font-medium leading-tight {compact
					? 'text-[10px]'
					: 'text-[12px]'}"
				title={node.label}
			>
				{node.label}
			</div>
			<!--
				Sources keep their kind label even when compact. Whether a source is a
				managed Kafka source or an adopted relation decides whether StreamBuild
				owns the data, which is exactly the fact worth knowing on a graph that
				marks something as read-but-not-rebuilt. Models can afford to drop it;
				their kind is already carried by the icon badge.
			-->
			{#if showKind}
				<div
					class="mt-[3px] truncate font-mono uppercase tracking-[0.1em] {compact
						? 'text-[8.5px]'
						: 'text-[9px]'}"
					style:color={deploymentColour ?? 'var(--sb-text-faint)'}
				>
					{node.kindLabel}
				</div>
			{/if}
			{#if showRelation && node.label !== node.sublabel}
				<div
					class="text-[var(--sb-text-faint)] mt-[2px] truncate font-mono text-[10px]"
					title={node.sublabel}
				>
					{node.sublabel}
				</div>
			{/if}
		</div>
	</div>

	{#if hasDetail}
		<div
			class="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 border-t border-[var(--border-subtle)] pt-1.5"
		>
			<!--
				The note takes part in the layout rather than floating over it. As an
				absolutely positioned chip it simply covered whatever detail sat
				underneath. This row already wraps, so height already varies with
				content and the graph layout measures it.
			-->
			{#if showAnchor}
				<span
					class="inline-flex items-center gap-1 font-mono text-[10px]"
					style:color={node.anchor === 'eligible' ? 'var(--sb-secondary)' : 'var(--sb-text-faint)'}
					title={ANCHOR_REASON[node.anchor ?? 'view']}
				>
					{#if node.anchor === 'eligible'}<AnchorIcon size={10} />anchor{:else}{node.anchor ===
						'aggregate'
							? 'aggregate'
							: node.anchor === 'mutable_ref'
								? 'mutable ref'
								: 'anchor never'}{/if}
				</span>
			{/if}
			{#if showChecks}
				<span class="font-mono text-[10px]" style:color={checkColour}>
					{node.totalChecks - node.failingChecks - node.warningChecks}/{node.totalChecks} audits
				</span>
			{/if}
			{#if showRows}
				<span class="text-muted-foreground font-mono text-[10px]"
					>{formatCompact(node.rows ?? 0)} rows</span
				>
			{/if}
			{#if showRate}
				<span class="font-mono text-[10px]" style:color="var(--sb-secondary)"
					>{formatRate(node.rowsPerSecond ?? 0)}</span
				>
			{/if}
			{#if node.drift}
				<span
					class="inline-flex items-center gap-1 font-mono text-[10px]"
					style:color="var(--sb-stale)"
					title="Definition changed since the last applied build"
				>
					<GitCompareIcon size={10} /> drift
				</span>
			{/if}
			{#if note}
				<span
					class="ml-auto shrink-0 rounded-[3px] px-1.5 py-[1px] font-mono text-[9px] leading-none"
					style:background="color-mix(in srgb, {note.tone === 'warn'
						? 'var(--sb-warning)'
						: 'var(--sb-secondary)'} 18%, transparent)"
					style:color={note.tone === 'warn' ? 'var(--sb-warning)' : 'var(--sb-secondary)'}
				>
					{note.text}
				</span>
			{/if}
		</div>
	{/if}

	<Handle type="source" position={Position.Right} class="!border-border !bg-muted !h-2 !w-2" />
</div>
