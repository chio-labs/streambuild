<script lang="ts">
	import { goto } from '$app/navigation';
	import AppTopbar from '$lib/presentation/components/app-topbar.svelte';
	import Button from '$ui-kit/button/button.svelte';
	import Checkbox from '$ui-kit/checkbox/checkbox.svelte';
	import { getProject } from '$lib/api/main/project/get-project';
	import { can } from '$lib/auth/main/can';
	import { modelsInPipeline } from '$lib/domain/main/lookups/models-in-pipeline';
	import { sourceByName } from '$lib/domain/main/lookups/source-by-name';
	import { anchorCount } from '$lib/domain/main/pipelines/anchor-count';
	import { pipelineFreshness } from '$lib/domain/main/pipelines/pipeline-freshness';
	import { auditCounts } from '$lib/domain/main/quality/audit-counts';
	import { auditsForModel } from '$lib/domain/main/quality/audits-for-model';
	import { formatRate } from '$lib/formatting/main/format-rate';
	import type { Audit, Project } from '$lib/domain/types';
	import DestructionDialog from './destruction-dialog.svelte';
	import { createDestructionState } from './state.svelte';
	import type { PipelineModeFilter } from './types';

	const project: Project = getProject();
	const destruction = createDestructionState();
	const modeFilters: { value: PipelineModeFilter; label: string }[] = [
		{ value: 'all', label: 'All' },
		{ value: 'direct', label: 'Direct' },
		{ value: 'virtual', label: 'Virtual' }
	];
	let modeFilter = $state<PipelineModeFilter>('all');
	let selected = $state<ReadonlySet<string>>(new Set());

	// A pipeline is the project's real top-level unit: `stb discover` returns
	// nothing but pipeline names, and `pipeline:<name>` is one of only two
	// selector forms. It is not a folder convention.
	const rows = $derived(
		project.pipelines.map((pipeline) => {
			const models: ReturnType<typeof modelsInPipeline> = modelsInPipeline(project, pipeline.name);
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
	const filteredRows = $derived(
		modeFilter === 'all' ? rows : rows.filter((row) => row.pipeline.mode === modeFilter)
	);
	const modeCounts = $derived({
		all: rows.length,
		direct: rows.filter((row) => row.pipeline.mode === 'direct').length,
		virtual: rows.filter((row) => row.pipeline.mode === 'virtual').length
	});
	const buildablePipelineNames = $derived(
		rows
			.filter((row) =>
				can(row.pipeline.mode === 'direct' ? 'build.direct.run' : 'deployment.create', row.pipeline.name)
			)
			.map((row) => row.pipeline.name)
	);
	const destroyablePipelineNames = $derived(
		rows
			.filter((row) => can('pipeline.destroy', row.pipeline.name))
			.map((row) => row.pipeline.name)
	);
	const selectablePipelineNames = $derived(
		filteredRows
			.filter(
				(row) =>
					buildablePipelineNames.includes(row.pipeline.name) ||
					destroyablePipelineNames.includes(row.pipeline.name)
			)
			.map((row) => row.pipeline.name)
	);
	const selectedBuildableNames = $derived(
		buildablePipelineNames.filter((name) => selected.has(name))
	);
	const selectedDestroyableNames = $derived(
		destroyablePipelineNames.filter((name) => selected.has(name))
	);
	const allCurrentSelected = $derived(
		selectablePipelineNames.length > 0 &&
			selectablePipelineNames.every((name) => selected.has(name))
	);
	const someCurrentSelected = $derived(
		!allCurrentSelected && selectablePipelineNames.some((name) => selected.has(name))
	);
	const resetAllowed = $derived(can('target.reset'));
	const dependentPermissionsAvailable = $derived(
		destruction.plan?.requiredDependentPipelines.every((name) => can('pipeline.destroy', name)) ??
			true
	);

	function togglePipeline(name: string): void {
		const next: Set<string> = new Set(selected);
		if (next.has(name)) next.delete(name);
		else next.add(name);
		selected = next;
	}

	function setCurrentPipelines(names: string[], checked: boolean): void {
		const next: Set<string> = new Set(selected);
		for (const name of names) {
			if (checked) next.add(name);
			else next.delete(name);
		}
		selected = next;
	}

	function openBuildPlan(): void {
		const parameters: URLSearchParams = new URLSearchParams();
		for (const name of [...selectedBuildableNames].sort()) {
			parameters.append('select', `pipeline:${name}`);
		}
		void goto(`/plan?${parameters.toString()}`);
	}

	function openDestroyPlan(): void {
		void destruction.start('destroy_pipelines', selectedDestroyableNames);
	}

	function openResetPlan(): void {
		void destruction.start('reset_target');
	}

</script>

<AppTopbar title="Pipelines">
	<Button
		size="sm"
		class="font-mono text-[10.5px]"
		disabled={selectedBuildableNames.length === 0}
		title={selectedBuildableNames.length === 0
			? 'Select pipelines you have permission to build'
			: 'Review the selected pipelines in Plan'}
		onclick={openBuildPlan}
	>
		Build{selectedBuildableNames.length > 0 ? ` (${selectedBuildableNames.length})` : ''}
	</Button>
	<Button
		variant="outline"
		size="sm"
		class="font-mono text-[10.5px]"
		disabled={!resetAllowed}
		title={resetAllowed ? 'Plan a reset of the entire target' : 'Requires the target.reset permission'}
		onclick={openResetPlan}
	>
		Reset target
	</Button>
	<Button
		variant="destructive"
		size="sm"
		class="font-mono text-[10.5px]"
		disabled={selectedDestroyableNames.length === 0}
		title={selectedDestroyableNames.length === 0
			? 'Select pipelines you have permission to destroy'
			: undefined}
		onclick={openDestroyPlan}
	>
		Destroy{selectedDestroyableNames.length > 0 ? ` (${selectedDestroyableNames.length})` : ''}
	</Button>
</AppTopbar>

<div class="min-h-0 flex-1 overflow-auto">
	<div class="flex items-center gap-2 border-b border-border px-[18px] py-2">
		<span class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]">
			Mode
		</span>
		<div
			class="flex overflow-hidden rounded-[3px] border border-border"
			role="group"
			aria-label="Filter pipelines by mode"
		>
			{#each modeFilters as filter, index (filter.value)}
				<button
					type="button"
					aria-pressed={modeFilter === filter.value}
					class="px-2.5 py-1 font-mono text-[10.5px] transition-colors {index > 0
						? 'border-l border-border'
						: ''} {modeFilter === filter.value
						? 'bg-[var(--sb-hover)] text-foreground'
						: 'text-muted-foreground hover:text-foreground'}"
					onclick={() => (modeFilter = filter.value)}
				>
					{filter.label}
					<span class="text-[var(--sb-text-faint)] pl-1">{modeCounts[filter.value]}</span>
				</button>
			{/each}
		</div>
		<span class="text-[var(--sb-text-faint)] ml-auto font-mono text-[10.5px]">
			{filteredRows.length} shown
		</span>
	</div>
	<table class="sb-list w-full text-left">
		<thead>
			<tr class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]">
				<th class="w-10 py-2 pl-[18px] pr-1 font-normal">
					<Checkbox
						checked={allCurrentSelected}
						indeterminate={someCurrentSelected}
						disabled={selectablePipelineNames.length === 0}
						aria-label="Select all actionable pipelines in the current table"
						onCheckedChange={(checked) =>
							setCurrentPipelines(selectablePipelineNames, checked === true)}
					/>
				</th>
				<th class="px-3 py-2 font-normal">Pipeline</th>
				<th class="px-3 py-2 font-normal">Mode</th>
				<th class="px-3 py-2 font-normal">Source</th>
				<th class="px-3 py-2 font-normal">Boundary</th>
				<th class="px-3 py-2 font-normal">Models</th>
				<th class="px-3 py-2 font-normal">Anchors</th>
				<th class="px-3 py-2 font-normal">Audits</th>
				<th class="px-3 py-2 font-normal">Ingest</th>
				<th class="px-3 py-2 pr-[18px] font-normal">Expected freshness</th>
			</tr>
		</thead>
		<tbody>
			{#each filteredRows as row (row.pipeline.name)}
				<tr>
					<td class="py-2 pl-[18px] pr-1">
						<Checkbox
							checked={selected.has(row.pipeline.name)}
							disabled={!selectablePipelineNames.includes(row.pipeline.name)}
							aria-label="Select {row.pipeline.name} for an action"
							title={selectablePipelineNames.includes(row.pipeline.name)
								? undefined
								: 'Requires build or pipeline.destroy permission for this pipeline'}
							onCheckedChange={() => togglePipeline(row.pipeline.name)}
						/>
					</td>
					<td class="px-3">
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
						<span
							class="sb-tag code"
							style:color={row.pipeline.mode === 'virtual'
								? 'var(--primary)'
								: 'var(--sb-text-faint)'}>{row.pipeline.mode}</span
						>
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
						{#if row.freshness.monitored === 0}
							<span class="text-muted-foreground text-[11px]">Not monitored</span>
						{:else}
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
							{#each Array(row.freshness.unknown) as _, index (`u${index}`)}
								<span class="flex-1 bg-[var(--sb-border-strong)]" title="not monitored"></span>
								{/each}
							</div>
							<span class="text-muted-foreground code text-[11px]"
								>{row.freshness.fresh} fresh{row.freshness.lagging
									? ` · ${row.freshness.lagging} late`
									: ''}{row.freshness.stalled ? ` · ${row.freshness.stalled} stale` : ''}</span
							>
						</div>
						{/if}
					</td>
				</tr>
			{/each}
			{#if filteredRows.length === 0}
				<tr>
					<td colspan="10" class="text-[var(--sb-text-faint)] px-[18px] py-8 text-center font-mono text-[11px]">
						No pipelines match this mode
					</td>
				</tr>
			{/if}
		</tbody>
	</table>
</div>

<DestructionDialog
	state={destruction}
	{dependentPermissionsAvailable}
/>
