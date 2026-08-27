<script lang="ts">
	import type { Model } from '$lib/domain/types';

	type ModelSemanticDrift = Model['live']['semanticDrift'];
	type DriftStatus = ModelSemanticDrift['status'];
	type Props = { drift: ModelSemanticDrift };

	let { drift }: Props = $props();

	const labelByStatus: Readonly<Record<DriftStatus, string>> = {
		in_sync: 'In sync',
		drift: 'Drift detected',
		unavailable: 'Not comparable'
	};
	const colourByStatus: Readonly<Record<DriftStatus, string>> = {
		in_sync: 'var(--sb-success)',
		drift: 'var(--sb-warning)',
		unavailable: 'var(--sb-text-faint)'
	};
</script>

<section data-testid="model-semantic-drift" class="overflow-hidden rounded-[4px] border border-border">
	<header class="bg-[var(--sb-surface-low)] flex flex-wrap items-start gap-3 border-b border-border px-3.5 py-3">
		<div>
			<div class="font-mono text-[11px] font-medium uppercase tracking-[0.12em]">Drift</div>
			<div class="text-muted-foreground mt-0.5 text-[11.5px]">
				Live warehouse vs current compiled definition
			</div>
		</div>
		<span
			class="ml-auto rounded-[3px] border border-current px-2 py-1 font-mono text-[10px] uppercase"
			style:color={colourByStatus[drift.status]}
		>
			{labelByStatus[drift.status]}
		</span>
		<p class="basis-full text-[12px] leading-relaxed" style:color={colourByStatus[drift.status]}>
			{drift.message}
		</p>
	</header>

	{#if drift.status === 'unavailable'}
		<div class="text-muted-foreground px-3.5 py-4 text-[12px]">
			No schema, query, or physical configuration diff is shown because there is no live relation
			to compare. This is not a last-applied-vs-current comparison.
		</div>
	{:else}
		<div class="divide-y divide-[var(--border-subtle)]">
			<section class="p-3.5">
				<div class="mb-2 flex items-center gap-2">
					<h3 class="font-mono text-[10.5px] uppercase tracking-[0.12em]">Schema drift</h3>
					<span class="ml-auto font-mono text-[10px]" style:color={colourByStatus[drift.schema.status]}>
						{labelByStatus[drift.schema.status]}
					</span>
				</div>
				{#if drift.schema.changes.length === 0}
					<p class="text-muted-foreground text-[11.5px]">Live column names, types, and defaults match.</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-left font-mono text-[10.5px]">
							<thead class="text-[var(--sb-text-faint)]">
								<tr><th class="pb-1.5 font-normal">Column</th><th class="pb-1.5 font-normal">Live</th><th class="pb-1.5 font-normal">Current compiled</th></tr>
							</thead>
							<tbody>
								{#each drift.schema.changes as change (change.column)}
									<tr class="border-t border-[var(--border-subtle)]">
										<td class="py-1.5 pr-3">{change.column}</td>
										<td class="py-1.5 pr-3" style:color="var(--sb-error)">{change.live ?? 'missing'}</td>
										<td class="py-1.5" style:color="var(--sb-success)">{change.compiled ?? 'removed'}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>

			<section class="p-3.5">
				<div class="mb-2 flex items-center gap-2">
					<h3 class="font-mono text-[10.5px] uppercase tracking-[0.12em]">Query drift</h3>
					<span class="text-[var(--sb-text-faint)] font-mono text-[10px]">{drift.query.relationName}</span>
					<span class="ml-auto font-mono text-[10px]" style:color={colourByStatus[drift.query.status]}>
						{labelByStatus[drift.query.status]}
					</span>
				</div>
				{#if drift.query.status === 'unavailable'}
					<p class="text-muted-foreground text-[11.5px]">The live query relation is missing; no query diff is possible.</p>
				{:else if drift.query.unifiedDiff}
					<pre class="bg-[var(--sb-inset)] max-h-64 overflow-auto rounded-[3px] p-2.5 font-mono text-[10.5px] leading-relaxed">{drift.query.unifiedDiff}</pre>
				{:else}
					<p class="text-muted-foreground text-[11.5px]">Canonical live and compiled queries match.</p>
				{/if}
			</section>

			<section class="p-3.5">
				<div class="mb-2 flex items-center gap-2">
					<h3 class="font-mono text-[10.5px] uppercase tracking-[0.12em]">Physical configuration drift</h3>
					<span class="ml-auto font-mono text-[10px]" style:color={colourByStatus[drift.physicalConfiguration.status]}>
						{labelByStatus[drift.physicalConfiguration.status]}
					</span>
				</div>
				<div class="grid gap-x-4 gap-y-1.5 font-mono text-[10.5px] sm:grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)]">
					<div class="text-[var(--sb-text-faint)] hidden sm:block"></div><div class="text-[var(--sb-text-faint)] hidden sm:block">Live</div><div class="text-[var(--sb-text-faint)] hidden sm:block">Current compiled</div>
					{#each drift.physicalConfiguration.changes as change (change.field)}
						<div class="pt-1 text-[var(--sb-text-faint)]">{change.field}</div>
						<div class:font-medium={change.status === 'drift'} style:color={change.status === 'drift' ? 'var(--sb-error)' : undefined}>{change.live}</div>
						<div class:font-medium={change.status === 'drift'} style:color={change.status === 'drift' ? 'var(--sb-success)' : undefined}>{change.compiled}</div>
					{/each}
				</div>
			</section>
		</div>
	{/if}
</section>
