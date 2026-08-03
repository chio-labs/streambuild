<script lang="ts">
	import { page } from '$app/state';
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left';
	import ReplaceIcon from '@lucide/svelte/icons/replace';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import SqlBlock from '$lib/components/sql-block.svelte';
	import type { SqlArtifact } from '$lib/components/sql-block.svelte';
	import StatusPill from '$lib/components/status-pill.svelte';
	import AnchorBadge from '$lib/components/anchor-badge.svelte';
	import FactRow from '$lib/components/fact-row.svelte';
	import SpanTrack from '$lib/components/span-track.svelte';
	import { getProject } from '$lib/api';
	import {
		auditsForModel,
		modelByName,
		reconstructionCoverage,
		rootSourceFor,
		testsForModel
	} from '$lib/domain/derive';
	import {
		formatAgo,
		formatBytes,
		formatDaySpan,
		formatDuration,
		formatInteger,
		formatTimestamp
	} from '$lib/domain/format';
	import {
		OWNERSHIP_LABEL,
		REF_TYPE_LABEL,
		type Model,
		type Project,
		type ReconstructionCoverage
	} from '$lib/domain/types';

	const project: Project = getProject();
	const modelName = $derived(page.params.name ?? '');
	const model = $derived<Model | undefined>(modelByName(project, modelName));

	const audits = $derived(model ? auditsForModel(project, model.name) : []);
	const tests = $derived(model ? testsForModel(project, model.name) : []);
	const source = $derived(model ? rootSourceFor(project, model) : undefined);
	const coverage = $derived<ReconstructionCoverage | undefined>(
		reconstructionCoverage(project).find((row) => row.modelName === modelName)
	);

	const artifacts = $derived.by((): SqlArtifact[] => {
		if (!model) return [];
		return [
			{ label: 'Model', code: model.sql.authored },
			{ label: 'Compiled', code: model.sql.compiled },
			{ label: 'Table DDL', code: model.sql.tableDdl },
			{
				label: 'MV DDL',
				code: model.sql.mvDdl
			},
			{ label: 'View DDL', code: model.sql.viewDdl }
		];
	});

	const upstream = $derived(model?.refs ?? []);
	const downstream = $derived(
		project.models.filter((candidate) =>
			candidate.refs.some((ref) => !ref.isSource && ref.name === modelName)
		)
	);
</script>

<AppTopbar title={modelName}>
	<a
		href="/plan?select={modelName}"
		class="bg-primary flex items-center gap-1.5 rounded-[4px] px-2.5 py-1.5 font-mono text-[11px] text-white"
	>
		<ReplaceIcon size={12} /> Plan rebuild
	</a>
</AppTopbar>

<div class="min-h-0 flex-1 overflow-y-auto">
	{#if !model}
		<div class="px-[18px] py-10 text-center">
			<p class="text-muted-foreground text-[13px]">No model named <code>{modelName}</code>.</p>
			<a href="/catalog" class="text-primary mt-2 inline-block font-mono text-[11.5px]"
				>← Back to catalog</a
			>
		</div>
	{:else}
		<div class="flex items-center gap-2.5 border-b border-border px-[18px] py-2.5">
			<a
				href="/catalog"
				class="text-muted-foreground hover:text-foreground flex items-center gap-1 font-mono text-[11px]"
				><ArrowLeftIcon size={12} /> Catalog</a
			>
			<span class="text-[var(--sb-text-faint)]">/</span>
			<a href="/pipelines/{model.pipeline}" class="text-primary font-mono text-[11px]"
				>{model.pipeline}</a
			>
			<div class="ml-auto flex items-center gap-3">
				<StatusPill status={model.status} />
				<AnchorBadge anchor={model.anchor} />
			</div>
		</div>

		<div class="grid gap-5 p-[18px]" style:grid-template-columns="minmax(0,1fr) 340px">
			<!-- main column -->
			<div class="flex min-w-0 flex-col gap-5">
				{#if model.description}
					<p class="text-muted-foreground text-[13px] leading-relaxed">{model.description}</p>
				{/if}

				<!-- All four artifacts StreamBuild produces. The MV DDL in particular
				     cannot be seen from the CLI at all. -->
				<div>
					<div
						class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						SQL artifacts
					</div>
					<SqlBlock {artifacts} maxHeight="420px" caption="pipelines/{model.pipeline}/{model.name}.sql" />
				</div>

				<!-- columns -->
				<div>
					<div
						class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Columns · exact ClickHouse types
					</div>
					<table class="sb-list w-full text-left">
						<thead>
							<tr
								class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]"
							>
								<th class="px-3 py-2 font-normal">Column</th>
								<th class="px-3 py-2 font-normal">Type</th>
								<th class="px-3 py-2 font-normal">Note</th>
							</tr>
						</thead>
						<tbody>
							{#each model.columns.filter((column) => column.replayRole === null) as column (column.name)}
								<tr>
									<td class="code px-3 text-[12px]">{column.name}</td>
									<td class="text-muted-foreground code px-3 text-[11.5px]">{column.type}</td>
									<td class="text-muted-foreground px-3 text-[11.5px]">{column.description ?? ''}</td>
								</tr>
							{/each}
							{#each model.columns.filter((column) => column.replayRole !== null) as column (column.name)}
								<tr class="sb-row-off">
									<td class="code px-3 text-[12px] italic">{column.name}</td>
									<td class="text-muted-foreground code px-3 text-[11.5px]">{column.type}</td>
									<td class="text-muted-foreground px-3 text-[11.5px]"
										>replay {column.replayRole}</td
									>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>

				<!-- lineage -->
				<div class="grid grid-cols-2 gap-5">
					<div>
						<div
							class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Upstream
						</div>
						{#if upstream.length === 0}
							<p class="text-muted-foreground text-[12px]">No references.</p>
						{/if}
						{#each upstream as ref (ref.name + ref.type)}
							<div class="flex items-center gap-2 border-b border-[var(--border-subtle)] py-1.5">
								<a
									class="text-primary font-mono text-[11.5px] hover:underline"
									href={ref.isSource ? `/sources/${ref.name}` : `/catalog/${ref.name}`}
									>{ref.name}</a
								>
								<span
									class="ml-auto font-mono text-[10px]"
									style:color={ref.type === 'mutable_reference'
										? 'var(--sb-warning)'
										: ref.type === 'driving_input'
											? 'var(--sb-secondary)'
											: 'var(--sb-text-faint)'}>{REF_TYPE_LABEL[ref.type]}</span
								>
							</div>
						{/each}
					</div>
					<div>
						<div
							class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Downstream
						</div>
						{#if downstream.length === 0}
							<p class="text-muted-foreground text-[12px]">
								Nothing reads this model.
							</p>
						{/if}
						{#each downstream as child (child.name)}
							<div class="flex items-center gap-2 border-b border-[var(--border-subtle)] py-1.5">
								<a class="text-primary font-mono text-[11.5px] hover:underline" href="/catalog/{child.name}"
									>{child.name}</a
								>
								<span class="ml-auto"><StatusPill status={child.status} /></span>
							</div>
						{/each}
					</div>
				</div>
			</div>

			<!-- right rail -->
			<div class="flex flex-col gap-5">
				<div>
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Live
					</div>
					{#if model.kind === 'view'}
						<p class="text-muted-foreground text-[11.5px]">No stored data.</p>
					{:else}
						<FactRow label="Rows" value={formatInteger(model.live.rows)} />
						<FactRow label="Disk" value={formatBytes(model.live.diskBytes)} />
						<FactRow label="Parts" value={String(model.live.parts)} />
						<FactRow
							label="Newest row"
							value={formatAgo(model.live.newestRowAt, project.capturedAt)}
							title={formatTimestamp(model.live.newestRowAt)}
						/>
						<FactRow
							label="Lag"
							value={model.live.lagSeconds === null
								? '—'
								: formatDuration(model.live.lagSeconds)}
							tone={model.status === 'stalled'
								? 'error'
								: model.status === 'lagging'
									? 'warning'
									: 'default'}
						/>
					{/if}
					<FactRow
						label="vs compiled"
						value={model.live.inSyncWithCompiled ? 'in sync' : 'drift'}
						tone={model.live.inSyncWithCompiled ? 'success' : 'warning'}
					/>
					<FactRow
						label="Ownership"
						value={OWNERSHIP_LABEL[model.live.ownership]}
						tone={model.live.ownership === 'direct' ? 'default' : 'warning'}
					/>
				</div>

				<div>
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Storage
					</div>
					<FactRow label="Kind" value={model.kind} />
					<FactRow label="Relation" value={model.relationName} mono />
					{#if model.mvRelationName}
						<FactRow label="Writing MV" value={model.mvRelationName} mono />
					{/if}
					<FactRow label="Engine" value={model.storage.engine ?? '—'} mono />
					<FactRow
						label="Order by"
						value={model.storage.orderBy.length ? model.storage.orderBy.join(', ') : '—'}
						mono
					/>
					<FactRow label="Partition by" value={model.storage.partitionBy ?? '—'} mono />
					<FactRow label="TTL" value={model.storage.ttl ?? '—'} mono />
					{#if model.storage.settings}
						{#each Object.entries(model.storage.settings) as [key, value] (key)}
							<FactRow label={key} value={value} mono />
						{/each}
					{/if}
				</div>

				<div>
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Replay
					</div>
					<div class="pb-2"><AnchorBadge anchor={model.anchor} showReason /></div>
					<FactRow label="Driving input" value={model.drivingInput ?? 'none'} mono />
					{#if source}
						<FactRow label="Root source" value={source.name} href="/sources/{source.name}" />
						<FactRow label="Boundary" value={source.boundaryMode} mono />
					{/if}
					{#if model.live.recordedCoverage}
						<FactRow
							label="Coverage from"
							value={formatTimestamp(model.live.recordedCoverage.from)}
						/>
						<FactRow label="Coverage to" value={formatTimestamp(model.live.recordedCoverage.to)} />
					{/if}
				</div>

				<!-- Reconstruction: the standing latent condition the CLI never reports. -->
				{#if coverage && coverage.state !== 'unknown' && source}
					<div>
						<div
							class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Reconstruction
						</div>
						{#if coverage.state === 'lossless'}
							<p class="text-[11.5px]" style:color="var(--sb-success)">
								{source.name} has no TTL — fully rebuildable.
							</p>
						{:else}
							{@const domainFrom = coverage.heldFrom ?? source.live.oldestEventAt}
							<div class="flex flex-col gap-1.5 pb-2">
								<div class="text-muted-foreground flex items-baseline gap-2 font-mono text-[10px]">
									<span>source retains</span><span class="ml-auto"
										>{formatDaySpan(coverage.retainedDays ?? 0)}</span
									>
								</div>
								<SpanTrack
									domainFrom={domainFrom}
									domainTo={project.capturedAt}
									height={14}
									bands={[
										{
											from: coverage.retainedFrom ?? domainFrom,
											to: project.capturedAt,
											colour: 'var(--sb-secondary)',
											opacity: 0.55
										}
									]}
								/>
								<div class="text-muted-foreground flex items-baseline gap-2 font-mono text-[10px]">
									<span>this model holds</span><span class="ml-auto"
										>{formatDaySpan(coverage.heldDays ?? 0)}</span
									>
								</div>
								<SpanTrack
									domainFrom={domainFrom}
									domainTo={project.capturedAt}
									height={14}
									bands={[
										{
											from: domainFrom,
											to: project.capturedAt,
											colour: 'var(--primary)',
											opacity: 0.5
										}
									]}
								/>
							</div>
							{#if coverage.state === 'truncating'}
								<p class="text-[11.5px]" style:color="var(--sb-warning)">
									{formatDaySpan(coverage.unreconstructableDays ?? 0)} more than {source.name} can
									rebuild
								</p>
							{:else}
								<p class="text-[11.5px]" style:color="var(--sb-success)">Fully rebuildable.</p>
							{/if}
						{/if}
					</div>
				{/if}

				<div>
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Checks
					</div>
					{#if audits.length === 0 && tests.length === 0}
						<p class="text-muted-foreground text-[12px]">None reference this model.</p>
					{/if}
					{#each audits as audit (audit.name)}
						<div class="flex items-center gap-2 border-b border-[var(--border-subtle)] py-1.5">
							<span
								class="h-1.5 w-1.5 shrink-0 rounded-[2px]"
								style:background={audit.result?.passed
									? 'var(--sb-success)'
									: audit.severity === 'warning'
										? 'var(--sb-warning)'
										: 'var(--sb-error)'}
							></span>
							<span class="truncate font-mono text-[11px]">{audit.name}</span>
							{#if audit.result && !audit.result.passed}
								<span class="ml-auto shrink-0 font-mono text-[10px]" style:color="var(--sb-error)"
									>{formatInteger(audit.result.failingRowCount)}</span
								>
							{/if}
						</div>
					{/each}
					{#each tests as test (test.name)}
						<div class="flex items-center gap-2 border-b border-[var(--border-subtle)] py-1.5">
							<span
								class="h-1.5 w-1.5 shrink-0 rounded-[2px]"
								style:background={test.result?.passed ? 'var(--sb-success)' : 'var(--sb-error)'}
							></span>
							<span class="truncate text-[11px]">{test.name}</span>
						</div>
					{/each}
				</div>
			</div>
		</div>
	{/if}
</div>
