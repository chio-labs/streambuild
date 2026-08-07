<script lang="ts">
	import GitCompareIcon from '@lucide/svelte/icons/git-compare';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Sparkline from '$lib/components/sparkline.svelte';
	import StatusPill from '$lib/components/status-pill.svelte';
	import { getProject } from '$lib/api';
	import { auditCounts, driftedModels, freshnessSummary, testCounts } from '$lib/domain/derive';
	import {
		formatAgo,
		formatCompact,
		formatDuration,
		formatInteger,
		formatRate,
		formatTimestamp
	} from '$lib/domain/format';
	import type { Project } from '$lib/domain/types';

	const project: Project = getProject();

	// Not "did last night's run succeed" — there are no runs. The question a
	// streaming operator actually has is: is data moving, and does the warehouse
	// still match my code?
	const freshness = $derived(freshnessSummary(project));
	const drifted = $derived(driftedModels(project));
	const audits = $derived(auditCounts(project.audits));
	const tests = $derived(testCounts(project.tests));

	// Overview must survive a project with 20+ sources, so the list is sorted
	// worst-lag-first and capped — you scan for what is NOT moving.
	// Partition ticks keep a fixed 30s visual threshold (within-source skew);
	// source-level status comes from the server-evaluated freshness policy.
	const LAG_WARN_SECONDS: number = 30;
	const SOURCE_VISIBLE_LIMIT: number = 6;
	const PARTITION_TICK_LIMIT: number = 12;

	let showAllSources = $state<boolean>(false);

	const sortedSources = $derived(
		[...project.sources].sort((a, b) => (b.live.lagSeconds ?? -1) - (a.live.lagSeconds ?? -1))
	);
	const visibleSources = $derived(
		showAllSources ? sortedSources : sortedSources.slice(0, SOURCE_VISIBLE_LIMIT)
	);
	const hiddenSourceCount = $derived(sortedSources.length - visibleSources.length);
	const totalThroughput = $derived(
		project.sources.reduce((sum, source) => sum + source.live.rowsPerSecond, 0)
	);
	const laggingSources = $derived(
		project.sources.filter(
			(source) => source.live.freshness === 'lagging' || source.live.freshness === 'stalled'
		)
	);

	const worstAudit = $derived(
		project.audits
			.filter((audit) => audit.result && !audit.result.passed)
			.sort((a, b) => (b.result?.failingRowCount ?? 0) - (a.result?.failingRowCount ?? 0))[0]
	);
</script>

<AppTopbar title="Overview" />

<div class="min-h-0 flex-1 overflow-y-auto">
	<!-- ── standing conditions banner ──────────────────────────────────────── -->
	{#if drifted.length}
		<div class="flex flex-col divide-y divide-[var(--border-subtle)] border-b border-border">
			{#if drifted.length}
				<div
					class="flex items-center gap-2.5 px-[18px] py-2.5"
					style:background="color-mix(in srgb, var(--sb-stale) 8%, transparent)"
				>
					<GitCompareIcon size={14} color="var(--sb-stale)" class="shrink-0" />
					<span class="text-[12.5px]">
						<strong class="font-medium">{drifted.length}</strong>
						{drifted.length === 1 ? 'model changed' : 'models changed'} since the last applied build
					</span>
					<span class="text-muted-foreground font-mono text-[11px]">
						{drifted.map((model) => model.name).join(' · ')}
					</span>
					<a
						href="/plan?{drifted.map((model) => `select=${model.name}`).join('&')}"
						class="text-primary ml-auto shrink-0 font-mono text-[11px] hover:underline"
						>Plan a rebuild →</a
					>
				</div>
			{/if}
		</div>
	{/if}

	<div class="flex flex-col gap-5 p-[18px]">
		<!-- ── ingest ──────────────────────────────────────────────────────── -->
		<div>
			<div
				class="text-[var(--sb-text-faint)] flex items-baseline gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
			>
				Ingest
				<span class="ml-auto normal-case tracking-normal">
					{formatRate(totalThroughput)} across {project.sources.length}
					{project.sources.length === 1 ? 'source' : 'sources'}
					{#if laggingSources.length}
						· <span style:color="var(--sb-warning)">{laggingSources.length} lagging</span>
					{/if}
				</span>
			</div>

			<!-- Sorted worst-lag-first and capped, so this holds up at 20+ sources:
			     the question is "what is not moving", not "list everything". -->
			<div class="overflow-hidden rounded-[4px] border border-border">
				{#each visibleSources as source (source.name)}
					<div
						class="flex items-center gap-4 border-b border-[var(--border-subtle)] px-3.5 py-2 last:border-b-0"
					>
						<div class="w-[168px] shrink-0">
							<a
								href="/sources/{source.name}"
								class="text-primary code truncate text-[12px] font-medium hover:underline"
								>{source.name}</a
							>
							<div class="text-[var(--sb-text-faint)] font-mono text-[10px]">
								{source.kind === 'kafka' ? 'kafka' : 'adopted'} · {source.boundaryMode}
							</div>
						</div>

						<div class="shrink-0"><Sparkline values={source.live.throughput} width={110} height={22} /></div>

						<div class="w-[70px] shrink-0 text-right font-mono text-[12px]" style:color="var(--sb-secondary)">
							{formatRate(source.live.rowsPerSecond)}
						</div>

						<div
							class="w-[76px] shrink-0 text-right font-mono text-[12px]"
							style:color={source.live.freshness === 'stalled'
								? 'var(--sb-error)'
								: source.live.freshness === 'lagging'
									? 'var(--sb-warning)'
									: 'var(--muted-foreground)'}
						>
							{source.live.lagSeconds === null ? '—' : formatDuration(source.live.lagSeconds)}
						</div>

						<!-- Per-partition ticks only while they stay legible; beyond that a
						     count plus the worst offender, since some topics have thousands. -->
						<div class="w-[186px] shrink-0">
							{#if source.live.partitions.length === 0}
								<span class="text-[var(--sb-text-faint)] font-mono text-[10px]">no partitions</span>
							{:else if source.live.partitions.length <= PARTITION_TICK_LIMIT}
								<div class="flex items-end gap-[3px]">
									{#each source.live.partitions as partition (partition.partition)}
										<span
											class="w-2.5 rounded-[1px]"
											style:height="{partition.lagSeconds > LAG_WARN_SECONDS ? 7 : 14}px"
											style:background={partition.lagSeconds > LAG_WARN_SECONDS
												? 'var(--sb-warning)'
												: 'var(--sb-secondary)'}
											title="p{partition.partition} · lag {formatDuration(partition.lagSeconds)}"
										></span>
									{/each}
								</div>
							{:else}
								{@const behind = source.live.partitions.filter(
									(partition) => partition.lagSeconds > LAG_WARN_SECONDS
								).length}
								<span class="text-muted-foreground whitespace-nowrap font-mono text-[10.5px]">
									{source.live.partitions.length} partitions
									{#if behind}<span style:color="var(--sb-warning)"> · {behind} behind</span>{/if}
								</span>
							{/if}
						</div>

						<div class="ml-auto shrink-0 text-right">
							<div class="font-mono text-[11px]">{formatCompact(source.live.rows)} retained</div>
							<div
								class="font-mono text-[10px]"
								style:color={source.retentionDays === null
									? 'var(--sb-success)'
									: 'var(--muted-foreground)'}
							>
								{source.retentionDays === null ? 'no TTL' : `${source.retentionDays}d horizon`}
							</div>
						</div>
					</div>
				{/each}

				{#if sortedSources.length > SOURCE_VISIBLE_LIMIT}
					<button
						class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] w-full px-3.5 py-2 text-left font-mono text-[11px]"
						onclick={() => (showAllSources = !showAllSources)}
					>
						{showAllSources
							? 'Show fewer'
							: `Show ${hiddenSourceCount} more keeping up →`}
					</button>
				{/if}
			</div>
		</div>

		<!-- ── freshness + quality ─────────────────────────────────────────── -->
		<div class="grid gap-5" style:grid-template-columns="minmax(0,1fr) 420px">
			<div>
				<div
					class="text-[var(--sb-text-faint)] flex items-baseline gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
				>
					Freshness <span class="normal-case tracking-normal">— {freshness.total} models</span>
				</div>
				<div class="rounded-[4px] border border-border p-3.5">
					<div class="flex h-3.5 gap-[3px] overflow-hidden rounded-[2px]">
						{#each Array(freshness.fresh) as _, index (`f${index}`)}
							<span class="flex-1 bg-[var(--sb-success)]" title="fresh"></span>
						{/each}
						{#each Array(freshness.lagging) as _, index (`l${index}`)}
							<span class="flex-1 bg-[var(--sb-warning)]" title="lagging"></span>
						{/each}
						{#each Array(freshness.stalled) as _, index (`s${index}`)}
							<span class="flex-1 bg-[var(--sb-error)]" title="stalled"></span>
						{/each}
						{#each Array(freshness.drift) as _, index (`d${index}`)}
							<span class="flex-1 bg-[var(--sb-stale)]" title="drift"></span>
						{/each}
					</div>
					<div class="flex flex-wrap gap-4 pt-2.5 font-mono text-[11px]">
						<span class="flex items-center gap-1.5"
							><span class="h-1.5 w-1.5 rounded-[2px] bg-[var(--sb-success)]"></span>{freshness.fresh}
							fresh</span
						>
						<span class="flex items-center gap-1.5"
							><span class="h-1.5 w-1.5 rounded-[2px] bg-[var(--sb-warning)]"></span>{freshness.lagging}
							lagging</span
						>
						<span class="flex items-center gap-1.5"
							><span class="h-1.5 w-1.5 rounded-[2px] bg-[var(--sb-error)]"></span>{freshness.stalled}
							stalled</span
						>
						<span class="flex items-center gap-1.5"
							><span class="h-1.5 w-1.5 rounded-[2px] bg-[var(--sb-stale)]"></span>{freshness.drift}
							drift</span
						>
					</div>

					{#if freshness.offenders.length}
						<div class="mt-3 border-t border-[var(--border-subtle)] pt-2.5">
							{#each freshness.offenders as model (model.name)}
								<div class="flex items-center gap-3 border-b border-[var(--border-subtle)] py-1.5 last:border-b-0">
									<a
										href="/catalog/{model.name}"
										class="text-primary code w-[190px] shrink-0 truncate text-[11.5px] hover:underline"
										>{model.name}</a
									>
									<span class="w-[84px] shrink-0"><StatusPill status={model.status} /></span>
									<span class="text-muted-foreground font-mono text-[11px]">
										{#if model.status === 'drift'}
											definition changed since last build
										{:else}
											last row {formatAgo(model.live.newestRowAt, project.capturedAt)}
										{/if}
									</span>
									<span class="text-[var(--sb-text-faint)] ml-auto shrink-0 font-mono text-[10.5px]"
										>{model.pipeline}</span
									>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<div>
				<div
					class="text-[var(--sb-text-faint)] flex items-baseline gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
				>
					Quality
					<span class="normal-case tracking-normal"
						>— checked {formatAgo(project.audits[0]?.result?.checkedAt ?? null, project.capturedAt)}</span
					>
				</div>
				<div class="rounded-[4px] border border-border p-3.5">
					<div class="grid grid-cols-2 gap-4">
						<div>
							<div class="text-[var(--sb-text-faint)] pb-1 font-mono text-[10px]">Audits</div>
							<div class="flex items-baseline gap-1.5">
								<span class="font-display text-[22px] font-semibold leading-none"
									>{audits.passing}</span
								>
								<span class="text-muted-foreground font-mono text-[12px]">/ {audits.total}</span>
							</div>
							<div class="flex gap-3 pt-1.5 font-mono text-[10.5px]">
								{#if audits.warning}
									<span style:color="var(--sb-warning)">{audits.warning} warn</span>
								{/if}
								{#if audits.failing}
									<span style:color="var(--sb-error)">{audits.failing} fail</span>
								{/if}
							</div>
						</div>
						<div>
							<div class="text-[var(--sb-text-faint)] pb-1 font-mono text-[10px]">Tests</div>
							<div class="flex items-baseline gap-1.5">
								<span class="font-display text-[22px] font-semibold leading-none"
									>{tests.passing}</span
								>
								<span class="text-muted-foreground font-mono text-[12px]">/ {tests.total}</span>
							</div>
							<div class="flex gap-3 pt-1.5 font-mono text-[10.5px]">
								{#if tests.failing}
									<span style:color="var(--sb-error)">{tests.failing} fail</span>
								{/if}
							</div>
						</div>
					</div>

					{#if worstAudit && worstAudit.result}
						<div class="mt-3 border-t border-[var(--border-subtle)] pt-2.5">
							<div class="flex items-center gap-2">
								<span
									class="h-1.5 w-1.5 shrink-0 rounded-[2px]"
									style:background={worstAudit.severity === 'warning'
										? 'var(--sb-warning)'
										: 'var(--sb-error)'}
								></span>
								<code class="truncate font-mono text-[11px]">{worstAudit.name}</code>
								<span class="ml-auto shrink-0 font-mono text-[10.5px]" style:color="var(--sb-error)"
									>{formatInteger(worstAudit.result.failingRowCount)} rows</span
								>
							</div>
						</div>
					{/if}
					<a href="/quality" class="text-primary mt-2.5 inline-block font-mono text-[11px] hover:underline"
						>Open Quality →</a
					>
				</div>
			</div>
		</div>

		<!-- ── snapshot footer ─────────────────────────────────────────────── -->
		<div
			class="text-[var(--sb-text-faint)] flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-border pt-3 font-mono text-[10.5px]"
		>
			<span>snapshot {formatTimestamp(project.capturedAt)}</span>
			<span>target {project.target} · database {project.database}</span>
			<span>adapter {project.adapter}</span>
			<span>direct mode</span>
			<span class="ml-auto"
				>{project.pipelines.length} pipelines · {project.models.length} models · {project.sources
					.length} sources</span
			>
		</div>
	</div>
</div>
