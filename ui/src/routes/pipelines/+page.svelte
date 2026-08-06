<script lang="ts">
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import { getProject } from '$lib/api';
	import {
		anchorCount,
		auditCounts,
		auditsForModel,
		modelsInPipeline,
		pipelineFreshness,
		sourceByName
	} from '$lib/domain/derive';
	import { formatRate } from '$lib/domain/format';
	import type { Audit, Project } from '$lib/domain/types';

	const project: Project = getProject();

	// A pipeline is the project's real top-level unit: `stb discover` returns
	// nothing but pipeline names, and `pipeline:<name>` is one of only two
	// selector forms. It is not a folder convention.
	const rows = $derived(
		project.pipelines.map((pipeline) => {
			const models = modelsInPipeline(project, pipeline.name);
			const audits: Audit[] = models.flatMap((model) => auditsForModel(project, model.name));
			return {
				pipeline,
				models,
				source: pipeline.sourceName ? sourceByName(project, pipeline.sourceName) : undefined,
				anchors: anchorCount(project, pipeline.name),
				audits: auditCounts(audits),
				freshness: pipelineFreshness(project, pipeline.name)
			};
		})
	);
</script>

<AppTopbar title="Pipelines" />

<div class="min-h-0 flex-1 overflow-y-auto">
	<table class="sb-list w-full text-left">
		<thead>
			<tr class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]">
				<th class="px-[18px] py-2 font-normal">Pipeline</th>
				<th class="px-3 py-2 font-normal">Source</th>
				<th class="px-3 py-2 font-normal">Boundary</th>
				<th class="px-3 py-2 font-normal">Models</th>
				<th class="px-3 py-2 font-normal">Anchors</th>
				<th class="px-3 py-2 font-normal">Audits</th>
				<th class="px-3 py-2 font-normal">Ingest</th>
				<th class="px-3 py-2 pr-[18px] font-normal">Freshness</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as row (row.pipeline.name)}
				<tr>
					<td class="px-[18px]">
						<a
							href="/pipelines/{row.pipeline.name}"
							class="text-primary code text-[12.5px] font-medium hover:underline"
							>{row.pipeline.name}</a
						>
						<div class="text-[var(--sb-text-faint)] code pt-0.5 text-[10.5px]">
							{row.pipeline.directory}
						</div>
					</td>
					<td class="px-3">
						{#if row.source}
							<a
								href="/sources/{row.source.name}"
								class="text-muted-foreground hover:text-foreground code text-[11.5px] hover:underline"
								>{row.source.name}</a
							>
							<div class="text-[var(--sb-text-faint)] pt-0.5 text-[10.5px]">
								{row.source.kind === 'kafka' ? 'managed Kafka' : 'adopted table'}
							</div>
						{:else}
							<span class="text-[var(--sb-text-faint)] text-[11.5px]">— view only</span>
						{/if}
					</td>
					<td class="px-3">
						{#if row.pipeline.boundaryMode}
							<span class="sb-tag code">{row.pipeline.boundaryMode}</span>
						{:else}
							<span class="text-[var(--sb-text-faint)] code text-[11px]">—</span>
						{/if}
					</td>
					<td class="code px-3 text-[12px]">{row.models.length}</td>
					<td class="px-3">
						<span
							class="code text-[12px]"
							style:color={row.anchors ? 'var(--sb-secondary)' : 'var(--sb-text-faint)'}
							>{row.anchors || '—'}</span
						>
					</td>
					<td class="px-3">
						{#if row.audits.total === 0}
							<span class="text-[var(--sb-text-faint)] code text-[11px]">—</span>
						{:else}
							<span
								class="code text-[12px]"
								style:color={row.audits.failing
									? 'var(--sb-error)'
									: row.audits.warning
										? 'var(--sb-warning)'
										: 'var(--sb-success)'}>{row.audits.passing}/{row.audits.total}</span
							>
						{/if}
					</td>
					<td class="px-3">
						{#if row.source}
							<span class="code text-[11.5px]" style:color="var(--sb-secondary)"
								>{formatRate(row.source.live.rowsPerSecond)}</span
							>
						{:else}
							<span class="text-[var(--sb-text-faint)] code text-[11px]">—</span>
						{/if}
					</td>
					<td class="px-3 pr-[18px]">
						<div class="flex items-center gap-2">
							<div class="flex h-3 w-[86px] gap-[2px] overflow-hidden rounded-[2px]">
								{#each Array(row.freshness.fresh) as _, index (`f${index}`)}
									<span class="flex-1 bg-[var(--sb-success)]"></span>
								{/each}
								{#each Array(row.freshness.lagging) as _, index (`l${index}`)}
									<span class="flex-1 bg-[var(--sb-warning)]"></span>
								{/each}
								{#each Array(row.freshness.stalled) as _, index (`s${index}`)}
									<span class="flex-1 bg-[var(--sb-error)]"></span>
								{/each}
								{#each Array(row.freshness.drift) as _, index (`d${index}`)}
									<span class="flex-1 bg-[var(--sb-stale)]"></span>
								{/each}
							</div>
							<span class="text-muted-foreground code text-[11px]"
								>{row.freshness.fresh}/{row.freshness.total}</span
							>
						</div>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
