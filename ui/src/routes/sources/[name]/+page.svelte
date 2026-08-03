<script lang="ts">
	import { page } from '$app/state';
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import FactRow from '$lib/components/fact-row.svelte';
	import Sparkline from '$lib/components/sparkline.svelte';
	import SpanTrack from '$lib/components/span-track.svelte';
	import SqlBlock from '$lib/components/sql-block.svelte';
	import type { SqlArtifact } from '$lib/components/sql-block.svelte';
	import { getProject } from '$lib/api';
	import { reconstructionCoverage, sourceByName } from '$lib/domain/derive';
	import * as SQL from '$lib/domain/sql';
	import {
		formatCompact,
		formatDaySpan,
		formatDuration,
		formatInteger,
		formatRate,
		formatTimestamp
	} from '$lib/domain/format';
	import { REPLAY_COLUMN_BY_ROLE, type Project, type ReplayRole } from '$lib/domain/types';

	const project: Project = getProject();
	const sourceName = $derived(page.params.name ?? '');
	const source = $derived(sourceByName(project, sourceName));

	const coverage = $derived(
		reconstructionCoverage(project).filter((row) => row.sourceName === sourceName)
	);
	const truncating = $derived(coverage.filter((row) => row.state === 'truncating'));

	/** Oldest instant across the source and every dependent model, so all tracks share one domain. */
	const domainFrom = $derived.by((): string => {
		const candidates: number[] = [new Date(source?.live.oldestEventAt ?? project.capturedAt).getTime()];
		for (const row of coverage) {
			if (row.heldFrom) candidates.push(new Date(row.heldFrom).getTime());
		}
		return new Date(Math.min(...candidates)).toISOString();
	});

	const artifacts = $derived.by((): SqlArtifact[] => {
		if (!source || source.kind !== 'kafka') return [];
		return [
			{ label: 'Kafka engine', code: SQL.KAFKA_ENGINE_DDL },
			{ label: 'Landing table', code: SQL.LANDING_TABLE_DDL },
			{ label: 'Landing MV', code: SQL.LANDING_MV_DDL }
		];
	});

	// ── partition scaling ────────────────────────────────────────────────────
	const LAG_WARN_SECONDS: number = 30;
	const PARTITION_PAGE_SIZE: number = 25;
	const LAG_BUCKET_COUNT: number = 48;

	let partitionQuery = $state<string>('');
	let partitionSort = $state<'lag' | 'id'>('lag');
	let partitionPage = $state<number>(0);

	const behindCount = $derived(
		(source?.live.partitions ?? []).filter(
			(partition) => partition.lagSeconds > LAG_WARN_SECONDS
		).length
	);

	/** Fixed-width buckets over the observed lag range, so shape survives any count. */
	const lagBuckets = $derived.by(
		(): { label: string; count: number; behind: boolean }[] => {
			const partitions = source?.live.partitions ?? [];
			const maxLag: number = Math.max(...partitions.map((item) => item.lagSeconds), 1);
			const width: number = maxLag / LAG_BUCKET_COUNT;
			const buckets = Array.from({ length: LAG_BUCKET_COUNT }, (_, index) => ({
				label: formatDuration(index * width),
				count: 0,
				behind: index * width > LAG_WARN_SECONDS
			}));
			for (const partition of partitions) {
				const index: number = Math.min(
					Math.floor(partition.lagSeconds / width),
					LAG_BUCKET_COUNT - 1
				);
				buckets[index].count += 1;
			}
			return buckets;
		}
	);

	const maxBucketCount = $derived(Math.max(...lagBuckets.map((bucket) => bucket.count), 1));

	const filteredPartitions = $derived.by(() => {
		const needle: string = partitionQuery.trim();
		const partitions = (source?.live.partitions ?? []).filter(
			(partition) => needle === '' || String(partition.partition).includes(needle)
		);
		return [...partitions].sort((a, b) =>
			partitionSort === 'lag' ? b.lagSeconds - a.lagSeconds : a.partition - b.partition
		);
	});

	const pageCount = $derived(
		Math.max(Math.ceil(filteredPartitions.length / PARTITION_PAGE_SIZE), 1)
	);
	const pagedPartitions = $derived(
		filteredPartitions.slice(
			Math.min(partitionPage, pageCount - 1) * PARTITION_PAGE_SIZE,
			(Math.min(partitionPage, pageCount - 1) + 1) * PARTITION_PAGE_SIZE
		)
	);

	const worstLagPartition = $derived.by((): number => {
		if (!source || source.live.partitions.length === 0) return 0;
		return Math.max(...source.live.partitions.map((partition) => partition.lagSeconds));
	});
</script>

<AppTopbar title={sourceName} />

<div class="min-h-0 flex-1 overflow-y-auto">
	{#if !source}
		<div class="px-[18px] py-10 text-center">
			<p class="text-muted-foreground text-[13px]">No source named <code>{sourceName}</code>.</p>
			<a href="/sources" class="text-primary mt-2 inline-block font-mono text-[11.5px]"
				>← Back to sources</a
			>
		</div>
	{:else}
		<div class="flex items-center gap-2.5 border-b border-border px-[18px] py-2.5">
			<a
				href="/sources"
				class="text-muted-foreground hover:text-foreground flex items-center gap-1 font-mono text-[11px]"
				><ArrowLeftIcon size={12} /> Sources</a
			>
			<span class="text-[var(--sb-text-faint)]">/</span>
			<span class="sb-tag">{source.kind === 'kafka' ? 'managed by StreamBuild' : 'adopted'}</span>
			<span class="sb-tag code">{source.boundaryMode}</span>
		</div>

		<div class="grid gap-5 p-[18px]" style:grid-template-columns="minmax(0,1fr) 320px">
			<div class="flex min-w-0 flex-col gap-5">
				<!-- ── RECONSTRUCTION HORIZON ──────────────────────────────────────
				     The single config value that defines the durability of everything
				     downstream. Stated with its consequence, in plain words. -->
				<div class="rounded-[4px] border border-border p-3.5">
					<div
						class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Reconstruction horizon
					</div>
					{#if source.retentionDays === null}
						<div class="font-mono text-[13px]" style:color="var(--sb-success)">
							no TTL — retained indefinitely
						</div>
					{:else}
						<div class="flex items-baseline gap-3">
							<span class="font-display text-[26px] font-semibold leading-none"
								>{source.retentionDays}d</span
							>
							<code class="text-muted-foreground font-mono text-[11.5px]">{source.ttl}</code>
						</div>
						{#if source.ttlFromProjectDefault}
							<div class="text-[var(--sb-text-faint)] pt-1.5 font-mono text-[10.5px]">
								inherited from [defaults].managed_source_ttl
							</div>
						{/if}
					{/if}
				</div>

				<!-- ── RECONSTRUCTION COVERAGE ─────────────────────────────────────
				     A standing latent condition: a model can hold more history than the
				     source can rebuild. The CLI never reports this. -->
				{#if coverage.length}
					<div>
						<div
							class="text-[var(--sb-text-faint)] flex items-baseline gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Reconstruction coverage
							<span class="normal-case tracking-normal">— held history vs rebuildable history</span>
						</div>

						<div class="overflow-hidden rounded-[4px] border border-border">
							<div class="border-b border-border px-3 py-2.5">
								<div
									class="text-muted-foreground flex items-baseline gap-2 pb-1 font-mono text-[10px]"
								>
									<span>{source.relationName} retains</span>
									<span class="ml-auto"
										>{source.retentionDays === null
											? 'unbounded'
											: formatDaySpan(source.retentionDays)}</span
									>
								</div>
								<SpanTrack
									{domainFrom}
									domainTo={project.capturedAt}
									height={16}
									bands={[
										{
											from: domainFrom,
											to: source.live.oldestEventAt,
											colour: 'transparent',
											hatch: true,
											label: 'aged out of retention'
										},
										{
											from: source.live.oldestEventAt,
											to: project.capturedAt,
											colour: 'var(--sb-secondary)',
											opacity: 0.55,
											label: 'retained'
										}
									]}
								/>
							</div>

							{#each coverage as row (row.modelName)}
								<div class="border-b border-[var(--border-subtle)] px-3 py-2 last:border-b-0">
									<div class="flex items-baseline gap-2 pb-1">
										<a
											href="/catalog/{row.modelName}"
											class="text-primary code text-[11.5px] hover:underline">{row.modelName}</a
										>
										<span class="text-muted-foreground ml-auto font-mono text-[10px]">
											holds {formatDaySpan(row.heldDays ?? 0)}
										</span>
										{#if row.state === 'truncating'}
											<span class="font-mono text-[10px]" style:color="var(--sb-warning)">
												· {formatDaySpan(row.unreconstructableDays ?? 0)} unreconstructable
											</span>
										{:else if row.state === 'matched'}
											<span class="font-mono text-[10px]" style:color="var(--sb-success)">· matched</span
											>
										{:else if row.state === 'lossless'}
											<span class="font-mono text-[10px]" style:color="var(--sb-success)"
												>· lossless</span
											>
										{/if}
									</div>
									<SpanTrack
										{domainFrom}
										domainTo={project.capturedAt}
										height={12}
										bands={[
											...(row.state === 'truncating' && row.heldFrom && row.retainedFrom
												? [
														{
															from: row.heldFrom,
															to: row.retainedFrom,
															colour: 'var(--sb-warning)',
															opacity: 0.6,
															label: 'held but not rebuildable'
														}
													]
												: []),
											{
												from:
													row.state === 'truncating' && row.retainedFrom
														? row.retainedFrom
														: (row.heldFrom ?? domainFrom),
												to: project.capturedAt,
												colour: 'var(--primary)',
												opacity: 0.5,
												label: 'rebuildable'
											}
										]}
									/>
								</div>
							{/each}
						</div>

						{#if truncating.length}
							<p class="pt-2 text-[12px]" style:color="var(--sb-warning)">
								{truncating.length}
								{truncating.length === 1 ? 'model holds' : 'models hold'} history
								{source.name} can no longer rebuild.
							</p>
						{/if}
					</div>
				{/if}

				<!-- ── PARTITIONS ──────────────────────────────────────────────────
				     Topics with hundreds or thousands of partitions are normal, so this
				     leads with the distribution and the stragglers, and pages the rest. -->
				{#if source.live.partitions.length}
					<div>
						<div
							class="text-[var(--sb-text-faint)] flex items-baseline gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Partitions
							<span class="normal-case tracking-normal">
								{formatInteger(source.live.partitions.length)} total{#if behindCount}
									· <span style:color="var(--sb-warning)">{behindCount} behind</span>{/if}
							</span>
						</div>

						<!-- lag distribution across every partition, one bar per bucket -->
						<div class="rounded-[4px] border border-border p-3">
							<div class="flex h-9 items-end gap-[2px]">
								{#each lagBuckets as bucket, bucketIndex (bucketIndex)}
									<div
										class="flex-1 rounded-[1px]"
										style:height="{bucket.count
											? Math.max(Math.sqrt(bucket.count / maxBucketCount) * 100, 12)
											: 3}%"
										style:background={bucket.behind ? 'var(--sb-warning)' : 'var(--sb-secondary)'}
										style:opacity={bucket.count ? 0.75 : 0.15}
										title="{bucket.label} · {bucket.count} partitions"
									></div>
								{/each}
							</div>
							<div
								class="text-[var(--sb-text-faint)] flex justify-between pt-1.5 font-mono text-[10px]"
							>
								<span>lag distribution</span>
								<span>{lagBuckets[0].label} → {lagBuckets[lagBuckets.length - 1].label}</span>
							</div>
						</div>

						<div class="flex items-center gap-2 py-2">
							<input
								bind:value={partitionQuery}
								placeholder="partition id…"
								class="bg-[var(--sb-inset)] w-[140px] rounded-[4px] border border-border px-2.5 py-1 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
							/>
							<div class="flex overflow-hidden rounded-[4px] border border-border">
								<button
									class="px-2.5 py-1 font-mono text-[10.5px] {partitionSort === 'lag'
										? 'bg-[var(--sb-hover)] text-foreground'
										: 'text-muted-foreground hover:text-foreground'}"
									onclick={() => (partitionSort = 'lag')}>worst lag</button
								>
								<button
									class="border-l border-border px-2.5 py-1 font-mono text-[10.5px] {partitionSort ===
									'id'
										? 'bg-[var(--sb-hover)] text-foreground'
										: 'text-muted-foreground hover:text-foreground'}"
									onclick={() => (partitionSort = 'id')}>id</button
								>
							</div>
							<span class="text-muted-foreground ml-auto font-mono text-[10.5px]">
								{filteredPartitions.length === source.live.partitions.length
									? `${formatInteger(filteredPartitions.length)} partitions`
									: `${formatInteger(filteredPartitions.length)} of ${formatInteger(source.live.partitions.length)}`}
							</span>
						</div>

						<table class="sb-list w-full text-left">
							<thead>
								<tr
									class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]"
								>
									<th class="px-3 py-2 font-normal">Partition</th>
									<th class="px-3 py-2 font-normal">Max offset</th>
									<th class="px-3 py-2 font-normal">Lag</th>
									<th class="px-3 py-2 font-normal">Newest event</th>
								</tr>
							</thead>
							<tbody>
								{#each pagedPartitions as partition (partition.partition)}
									<tr>
										<td class="code px-3 text-[12px]">{partition.partition}</td>
										<td class="text-muted-foreground code px-3 text-[11.5px]"
											>{formatInteger(partition.offset)}</td
										>
										<td class="code px-3 text-[11.5px]">
											<span
												style:color={partition.lagSeconds > LAG_WARN_SECONDS
													? 'var(--sb-warning)'
													: 'var(--foreground)'}>{formatDuration(partition.lagSeconds)}</span
											>
										</td>
										<td class="text-muted-foreground code px-3 text-[11.5px]"
											>{formatTimestamp(partition.newestEventAt)}</td
										>
									</tr>
								{/each}
							</tbody>
						</table>

						{#if pageCount > 1}
							<div class="flex items-center gap-2 pt-2">
								<button
									class="text-muted-foreground hover:text-foreground rounded-[4px] border border-border px-2.5 py-1 font-mono text-[10.5px] disabled:opacity-40"
									disabled={partitionPage === 0}
									onclick={() => (partitionPage -= 1)}>← prev</button
								>
								<span class="text-muted-foreground font-mono text-[10.5px]"
									>page {partitionPage + 1} of {pageCount}</span
								>
								<button
									class="text-muted-foreground hover:text-foreground rounded-[4px] border border-border px-2.5 py-1 font-mono text-[10.5px] disabled:opacity-40"
									disabled={partitionPage >= pageCount - 1}
									onclick={() => (partitionPage += 1)}>next →</button
								>
							</div>
						{/if}
					</div>
				{/if}

				<!-- managed object DDL -->
				{#if artifacts.length}
					<div>
						<div
							class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Managed objects
						</div>
						<SqlBlock {artifacts} maxHeight="300px" />
					</div>
				{/if}
			</div>

			<!-- right rail -->
			<div class="flex flex-col gap-5">
				<div>
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Live
					</div>
					<div class="pb-2"><Sparkline values={source.live.throughput} width={280} height={34} /></div>
					<FactRow label="Rate" value={formatRate(source.live.rowsPerSecond)} />
					<FactRow
						label="Lag"
						value={source.live.lagSeconds === null
							? 'n/a — no offset lineage'
							: formatDuration(source.live.lagSeconds)}
					/>
					<FactRow label="Retained rows" value={formatCompact(source.live.rows)} />
					<FactRow label="Newest event" value={formatTimestamp(source.live.newestEventAt)} />
					<FactRow label="Retained from" value={formatTimestamp(source.live.oldestEventAt)} />
				</div>

				<div>
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Configuration
					</div>
					<FactRow label="Kind" value={source.kind} mono />
					<FactRow label="Boundary" value={source.boundaryMode} mono />
					{#if source.brokerList}<FactRow label="Broker" value={source.brokerList} mono />{/if}
					{#if source.topic}<FactRow label="Topic" value={source.topic} mono />{/if}
					{#if source.consumerGroup}
						<FactRow label="Consumer group" value={source.consumerGroup} mono />
					{/if}
					{#if source.format}<FactRow label="Format" value={source.format} mono />{/if}
					<FactRow label="Read relation" value={source.relationName} mono />
					{#if source.settings}
						{#each Object.entries(source.settings) as [key, value] (key)}
							<FactRow label={key} value={value} mono />
						{/each}
					{/if}
				</div>

				{#if source.managedRelations.length}
					<div>
						<div
							class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Managed relations
						</div>
						{#each source.managedRelations as relation (relation.name)}
							<div class="border-b border-[var(--border-subtle)] py-2">
								<div class="code text-[11.5px]">{relation.name}</div>
								<div class="text-[var(--sb-text-faint)] pt-0.5 font-mono text-[10px]">
									{relation.engine} · {relation.note}
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<div>
						<div
							class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Adopted relation
						</div>
						<div class="code pb-1 text-[11.5px]">{source.relationName}</div>
					</div>
				{/if}

				{#if source.columnMapping}
					<div>
						<div
							class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
						>
							Replay column mapping
						</div>
						{#each Object.entries(source.columnMapping) as [role, column] (role)}
							<FactRow
								label={REPLAY_COLUMN_BY_ROLE[role as ReplayRole]}
								value={column ?? '—'}
								mono
							/>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
