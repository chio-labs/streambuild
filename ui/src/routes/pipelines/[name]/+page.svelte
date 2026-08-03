<script lang="ts">
	import { page } from '$app/state';
	import { replaceState } from '$app/navigation';
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left';
	import ReplaceIcon from '@lucide/svelte/icons/replace';
	import NetworkIcon from '@lucide/svelte/icons/network';
	import AnchorIcon from '@lucide/svelte/icons/anchor';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import PipelineGraph from '$lib/components/pipeline/pipeline-graph.svelte';
	import StatusPill from '$lib/components/status-pill.svelte';
	import FactRow from '$lib/components/fact-row.svelte';
	import Sparkline from '$lib/components/sparkline.svelte';
	import { getProject } from '$lib/api';
	import {
		auditCounts,
		auditsForModel,
		modelsInPipeline,
		pipelineByName,
		sourceByName,
		streamTree
	} from '$lib/domain/derive';
	import {
		formatAgo,
		formatCompact,
		formatDuration,
		formatRate,
		formatTimestamp
	} from '$lib/domain/format';
	import { REF_TYPE_LABEL, type ModelRef, type Project } from '$lib/domain/types';

	const project: Project = getProject();
	const pipelineName = $derived(page.params.name ?? '');
	const pipeline = $derived(pipelineByName(project, pipelineName));
	const source = $derived(pipeline?.sourceName ? sourceByName(project, pipeline.sourceName) : undefined);
	const tree = $derived(streamTree(project, pipelineName));
	const models = $derived(modelsInPipeline(project, pipelineName));

	// URL-addressable like every other view toggle, so a specific reading of a
	// pipeline is shareable.
	let view = $state<'tree' | 'graph'>(
		page.url.searchParams.get('view') === 'graph' ? 'graph' : 'tree'
	);

	function setView(next: 'tree' | 'graph'): void {
		view = next;
		const url = new URL(page.url);
		if (next === 'tree') url.searchParams.delete('view');
		else url.searchParams.set('view', next);
		replaceState(url, {});
	}

	/** Side references break the tree, so they are listed separately rather than faked into it. */
	const sideRefs = $derived.by((): { from: string; ref: ModelRef }[] => {
		const found: { from: string; ref: ModelRef }[] = [];
		for (const model of models) {
			for (const ref of model.refs) {
				if (ref.type !== 'driving_input') found.push({ from: model.name, ref });
			}
		}
		return found;
	});
</script>

<AppTopbar title={pipelineName}>
	<a
		href="/lineage?pipeline={pipelineName}"
		class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded-[4px] border border-border px-2.5 py-1.5 font-mono text-[11px]"
	>
		<NetworkIcon size={12} /> Lineage
	</a>
	<a
		href="/plan?select=pipeline:{pipelineName}"
		class="bg-primary flex items-center gap-1.5 rounded-[4px] px-2.5 py-1.5 font-mono text-[11px] text-white"
	>
		<ReplaceIcon size={12} /> Plan rebuild
	</a>
</AppTopbar>

<div class="min-h-0 flex-1 overflow-y-auto">
	{#if !pipeline}
		<div class="px-[18px] py-10 text-center">
			<p class="text-muted-foreground text-[13px]">No pipeline named <code>{pipelineName}</code>.</p>
			<a href="/pipelines" class="text-primary mt-2 inline-block font-mono text-[11.5px]"
				>← Back to pipelines</a
			>
		</div>
	{:else}
		<div class="flex items-center gap-2.5 border-b border-border px-[18px] py-2.5">
			<a
				href="/pipelines"
				class="text-muted-foreground hover:text-foreground flex items-center gap-1 font-mono text-[11px]"
				><ArrowLeftIcon size={12} /> Pipelines</a
			>
			<span class="text-[var(--sb-text-faint)]">/</span>
			<code class="font-mono text-[11px]">pipeline:{pipeline.name}</code>
			<span class="text-[var(--sb-text-faint)] ml-auto font-mono text-[11px]"
				>{pipeline.directory}</span
			>
		</div>

		<div class="grid gap-5 p-[18px]" style:grid-template-columns="minmax(0,1fr) 320px">
			<div class="flex min-w-0 flex-col gap-5">
				<!-- source header -->
				{#if source}
					<div class="rounded-[4px] border border-border p-3.5">
						<div class="flex items-start gap-4">
							<div class="min-w-0 flex-1">
								<div
									class="text-[var(--sb-text-faint)] pb-1 font-mono text-[10px] uppercase tracking-[0.14em]"
								>
									Source
								</div>
								<a
									href="/sources/{source.name}"
									class="text-primary font-mono text-[13px] font-medium hover:underline"
									>{source.name}</a
								>
								<div class="text-muted-foreground pt-1 font-mono text-[11px]">
									{source.kind === 'kafka' ? 'managed Kafka' : 'adopted table'} ·
									{source.topic ?? source.relationName} · {source.boundaryMode}
								</div>
							</div>
							<div class="shrink-0 text-right">
								<Sparkline values={source.live.throughput} width={130} height={28} />
								<div class="pt-1 font-mono text-[11px]" style:color="var(--sb-secondary)">
									{formatRate(source.live.rowsPerSecond)}
								</div>
							</div>
							<div class="w-[150px] shrink-0">
								<FactRow
									label="Lag"
									value={source.live.lagSeconds === null
										? '—'
										: formatDuration(source.live.lagSeconds)}
								/>
								<FactRow
									label="Retention"
									value={source.retentionDays === null ? 'none' : `${source.retentionDays}d`}
									tone={source.retentionDays === null ? 'success' : 'default'}
								/>
							</div>
						</div>
					</div>
				{:else}
					<div class="rounded-[4px] border border-border p-3.5">
						<div class="text-muted-foreground text-[12.5px]">View-only pipeline — no source.</div>
					</div>
				{/if}

				<!-- STREAM TREE: legible precisely because every table model has exactly
				     one driving input, making the driving graph a tree rooted at the source. -->
				<div>
					<div
						class="text-[var(--sb-text-faint)] flex items-center gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						{view === 'tree' ? 'Stream tree' : 'Pipeline graph'}
						<span class="normal-case tracking-normal"
							>{view === 'tree'
								? '— follows the driving input'
								: '— includes side references'}</span
						>
						<div class="ml-auto flex overflow-hidden rounded-[4px] border border-border">
							<button
								class="px-2.5 py-1 font-mono text-[10px] normal-case tracking-normal transition-colors {view ===
								'tree'
									? 'bg-[var(--sb-hover)] text-foreground'
									: 'text-muted-foreground hover:text-foreground'}"
								onclick={() => setView('tree')}>Tree</button
							>
							<button
								class="border-l border-border px-2.5 py-1 font-mono text-[10px] normal-case tracking-normal transition-colors {view ===
								'graph'
									? 'bg-[var(--sb-hover)] text-foreground'
									: 'text-muted-foreground hover:text-foreground'}"
								onclick={() => setView('graph')}>Graph</button
							>
						</div>
					</div>

					{#if view === 'graph'}
						<PipelineGraph {project} {pipelineName} />
					{:else}
					<div class="overflow-hidden rounded-[4px] border border-border">
						<div
							class="text-[var(--sb-text-faint)] bg-[var(--sb-surface-low)] flex items-center gap-3 border-b border-border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							<span class="w-[300px] shrink-0">Node</span>
							<span class="w-[112px] shrink-0">Engine</span>
							<span class="w-[210px] shrink-0">Relation</span>
							<span class="w-[62px] shrink-0 text-right">Rows</span>
							<span class="w-[84px] shrink-0">Status</span>
							<span class="w-[92px] shrink-0">Replay</span>
							<span class="flex-1"></span>
						</div>

						{#each tree as row (row.name)}
							<div
								class="flex items-stretch gap-3 border-b border-[var(--border-subtle)] px-3 py-2 last:border-b-0"
							>
								<div class="flex w-[300px] shrink-0 items-center overflow-hidden">
									{#each row.ancestorHasNext as hasNext, depth (depth)}
										<span class="sb-tree-guide {hasNext ? '' : 'sb-tree-guide-empty'}"></span>
									{/each}
									{#if row.depth > 0}
										<span
											class="sb-tree-guide sb-tree-guide-elbow {row.isLast
												? 'sb-tree-guide-last'
												: ''}"
										></span>
									{/if}
									{#if row.kind === 'source'}
										<span class="code truncate text-[12px]" style:color="var(--sb-text-faint)"
											>{row.name}</span
										>
									{:else if row.model}
										<a
											href="/catalog/{row.name}"
											class="text-primary code truncate text-[12px] hover:underline">{row.name}</a
										>
									{/if}
								</div>
								<span class="text-muted-foreground code w-[112px] shrink-0 truncate text-[10.5px]">
									{row.kind === 'source'
										? 'SOURCE'
										: (row.model?.storage.engine ?? 'VIEW').replace('()', '')}
								</span>
								<span class="text-muted-foreground code w-[210px] shrink-0 truncate text-[10.5px]">
									{row.kind === 'source' ? row.source?.relationName : row.model?.relationName}
								</span>
								<span class="text-muted-foreground code w-[62px] shrink-0 text-right text-[10.5px]">
									{row.kind === 'source'
										? formatCompact(row.source?.live.rows ?? 0)
										: row.model?.kind === 'view'
											? '—'
											: formatCompact(row.model?.live.rows ?? 0)}
								</span>
								<span class="w-[84px] shrink-0">
									{#if row.model}<StatusPill status={row.model.status} />{/if}
								</span>
								<span class="w-[92px] shrink-0">
									{#if row.model?.anchor === 'eligible'}
										<span
											class="inline-flex items-center gap-1 font-mono text-[10px]"
											style:color="var(--sb-secondary)"><AnchorIcon size={10} /> anchor</span
										>
									{:else if row.model}
										<span class="text-[var(--sb-text-faint)] font-mono text-[10px]"
											>{row.model.anchor === 'aggregate'
												? 'aggregate'
												: row.model.anchor === 'mutable_ref'
													? 'mutable ref'
													: row.model.anchor === 'never'
														? 'anchor never'
														: 'view'}</span
										>
									{/if}
								</span>
								<span class="flex-1"></span>
							</div>
						{/each}
					</div>
					{/if}
				</div>

				<!-- side references -->
				{#if sideRefs.length}
					<div>
						<div
							class="text-[var(--sb-text-faint)] flex items-baseline gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Side references
						</div>
						{#each sideRefs as item (item.from + item.ref.name)}
							<div class="flex items-center gap-2.5 border-b border-[var(--border-subtle)] py-2">
								<a href="/catalog/{item.from}" class="text-primary code text-[11.5px] hover:underline"
									>{item.from}</a
								>
								<span class="text-[var(--sb-text-faint)] font-mono text-[11px]">←</span>
								<a
									href={item.ref.isSource
										? `/sources/${item.ref.name}`
										: `/catalog/${item.ref.name}`}
									class="text-muted-foreground hover:text-foreground code text-[11.5px] hover:underline"
									>{item.ref.name}</a
								>
								<span
									class="ml-auto font-mono text-[10.5px]"
									style:color={item.ref.type === 'mutable_reference'
										? 'var(--sb-warning)'
										: 'var(--sb-text-faint)'}>{REF_TYPE_LABEL[item.ref.type]}</span
								>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<!-- right rail -->
			<div class="flex flex-col gap-5">
				<div>
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Definition
					</div>
					<FactRow label="Selector" value="pipeline:{pipeline.name}" mono />
					<FactRow label="Directory" value={pipeline.directory} mono />
					<FactRow label="Source" value={pipeline.sourceName ?? 'none'} mono />
					<FactRow label="Boundary" value={pipeline.boundaryMode ?? '—'} mono />
					<FactRow label="Models" value={String(models.length)} />
					<FactRow label="Database" value={project.database} mono />
					{#if pipeline.naming?.viewPrefix}
						<FactRow label="View prefix" value={pipeline.naming.viewPrefix} mono />
					{/if}
					{#if pipeline.naming?.tablePrefix}
						<FactRow label="Table prefix" value={pipeline.naming.tablePrefix} mono />
					{/if}
				</div>

				{#if source}
					<div>
						<div
							class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Source window
						</div>
						<FactRow label="Retained from" value={formatTimestamp(source.live.oldestEventAt)} />
						<FactRow label="Newest event" value={formatTimestamp(source.live.newestEventAt)} />
						<FactRow label="Retained rows" value={formatCompact(source.live.rows)} />
					</div>
				{/if}

				<div>
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Models
					</div>
					{#each models as model (model.name)}
						{@const counts = auditCounts(auditsForModel(project, model.name))}
						<div class="flex items-center gap-2 border-b border-[var(--border-subtle)] py-1.5">
							<a href="/catalog/{model.name}" class="text-primary code truncate text-[11.5px] hover:underline"
								>{model.name}</a
							>
							<span class="ml-auto shrink-0 font-mono text-[10px]">
								{#if counts.total}
									<span
										style:color={counts.failing
											? 'var(--sb-error)'
											: counts.warning
												? 'var(--sb-warning)'
												: 'var(--sb-success)'}>{counts.passing}/{counts.total}</span
									>
								{/if}
							</span>
							<span class="shrink-0 text-right font-mono text-[10px]"
								>{formatAgo(model.live.newestRowAt, project.capturedAt)}</span
							>
						</div>
					{/each}
				</div>
			</div>
		</div>
	{/if}
</div>
