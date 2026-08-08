<script lang="ts">
	import { page } from '$app/state';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import LineageCanvas from '$lib/components/lineage/lineage-canvas.svelte';
	import EdgeLegend from '$lib/components/lineage/edge-legend.svelte';
	import FactRow from '$lib/components/fact-row.svelte';
	import { fetchDeployment, getProject } from '$lib/api';
	import { buildLogicalGraph } from '$lib/domain/derive';
	import { formatBytes, formatCompact, formatInteger } from '$lib/domain/format';
	import type { DeploymentDetail, DeploymentModel, Graph, Project } from '$lib/domain/types';

	const project: Project = getProject();
	const deploymentId: string = $derived(page.params.id ?? '');

	let detail = $state<DeploymentDetail | null>(null);
	let loadError = $state<string | null>(null);

	$effect(() => {
		const id = deploymentId;
		let cancelled = false;
		detail = null;
		loadError = null;
		fetchDeployment(id)
			.then((payload) => {
				if (!cancelled) detail = payload;
			})
			.catch((error: unknown) => {
				if (!cancelled) loadError = String(error);
			});
		return () => {
			cancelled = true;
		};
	});

	/** Deployment relation names are physical; the graph is keyed by model name. */
	const modelByRelation: Map<string, string> = $derived(
		new Map(project.models.map((model) => [model.relationName, model.name]))
	);

	const deploymentModels: DeploymentModel[] = $derived(detail?.models ?? []);

	const modelNames: Set<string> = $derived(
		new Set(
			deploymentModels
				.map((model) => modelByRelation.get(model.logicalName))
				.filter((name): name is string => name !== undefined)
		)
	);

	function suffixOf(relation: string | null): string {
		if (relation === null) return '—';
		const deploymentPart = relation.split('__').at(-1) ?? relation;
		return deploymentPart.split('_').at(-1) ?? deploymentPart;
	}

	/**
	 * The project graph narrowed to this deployment plus one hop upstream, with
	 * each node's sublabel replaced by its physical switchover. Reusing the
	 * lineage canvas keeps one visual language for "what depends on what".
	 */
	const scoped = $derived.by((): Graph => {
		const full: Graph = buildLogicalGraph(project);
		const comparisonByModel = new Map<string, DeploymentModel>();
		for (const model of deploymentModels) {
			const name = modelByRelation.get(model.logicalName);
			if (name !== undefined) comparisonByModel.set(name, model);
		}

		const keep = new Set<string>();
		for (const node of full.nodes) {
			if (node.logicalType !== 'source' && modelNames.has(node.logicalName)) keep.add(node.id);
		}
		for (const edge of full.edges) {
			if (keep.has(edge.target)) keep.add(edge.source);
		}

		return {
			nodes: full.nodes
				.filter((node) => keep.has(node.id))
				.map((node) => {
					const comparison = comparisonByModel.get(node.logicalName);
					if (comparison === undefined) return node;
					return {
						...node,
						sublabel: comparison.isNew
							? `new · ${suffixOf(comparison.stagedRelation)}`
							: `${suffixOf(comparison.liveRelation)} → ${suffixOf(comparison.stagedRelation)}`,
						rows: comparison.stagedRows
					};
				}),
			edges: full.edges.filter((edge) => keep.has(edge.source) && keep.has(edge.target))
		};
	});

	const totalStagedRows: number = $derived(
		deploymentModels.reduce((total, model) => total + model.stagedRows, 0)
	);
	const totalLiveRows: number = $derived(
		deploymentModels.reduce((total, model) => total + (model.liveRows ?? 0), 0)
	);
	const rowDelta: number = $derived(totalStagedRows - totalLiveRows);
	const newModelCount: number = $derived(
		deploymentModels.filter((model) => model.isNew).length
	);
</script>

<AppTopbar title={deploymentId} />

<div class="min-h-0 flex-1 overflow-y-auto px-[18px] py-4">
	{#if loadError !== null}
		<div class="rounded-md border border-[var(--sb-border)] p-6 text-[13px]" style:color="var(--sb-error)">
			{loadError}
		</div>
	{:else if detail === null}
		<div class="text-muted-foreground text-[13px]">loading deployment…</div>
	{:else}
		<div class="flex items-center gap-2 pb-3">
			<a href="/deployments" class="text-muted-foreground hover:text-foreground text-[12px]"
				>← deployments</a
			>
			<span
				class="sb-tag code"
				style:color={detail.state === 'active'
					? 'var(--sb-secondary)'
					: detail.state === 'staged'
						? 'var(--sb-warn)'
						: 'var(--sb-text-faint)'}>{detail.state}</span
			>
			{#if detail.state === 'staged'}
				<span class="text-[var(--sb-text-faint)] text-[11.5px]">
					nothing changes until this is promoted
				</span>
			{/if}
		</div>

		<div class="flex flex-col gap-4 lg:flex-row">
			<div class="min-w-0 flex-1 overflow-hidden rounded-[4px] border border-border">
				<div class="flex items-center gap-3 border-b border-border px-3 py-1.5">
					<EdgeLegend compact />
					<span class="text-[var(--sb-text-faint)] ml-auto font-mono text-[10px]">
						node shows live → staged
					</span>
				</div>
				<div style:height="520px">
					<LineageCanvas
						{project}
						graph={scoped}
						groupMode="none"
						layoutSalt={deploymentId}
					/>
				</div>
			</div>

			<div class="flex w-full shrink-0 flex-col gap-4 lg:w-[320px]">
				<div class="rounded-[4px] border border-border">
					<div
						class="text-[var(--sb-text-faint)] border-b border-border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em]"
					>
						Deployment
					</div>
					<div class="px-3 py-1.5">
						<FactRow label="Models" value={formatInteger(detail.modelCount)} mono />
						<FactRow label="Relations" value={formatInteger(detail.relationCount)} mono />
						<FactRow label="New models" value={formatInteger(newModelCount)} mono />
						<FactRow label="Storage" value={formatBytes(detail.bytes)} mono />
						<FactRow label="Created" value={detail.createdAt ?? '—'} mono />
						<FactRow label="Published" value={detail.publishedAt ?? 'not promoted'} mono />
					</div>
				</div>

				<div class="rounded-[4px] border border-border">
					<div
						class="text-[var(--sb-text-faint)] border-b border-border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em]"
					>
						Rows versus live
					</div>
					<div class="px-3 py-1.5">
						<FactRow label="Staged" value={formatCompact(totalStagedRows)} mono />
						<FactRow label="Live" value={formatCompact(totalLiveRows)} mono />
						<FactRow
							label="Delta"
							value={`${rowDelta >= 0 ? '+' : ''}${formatInteger(rowDelta)}`}
							mono
						/>
					</div>
				</div>

				{#if detail.state === 'superseded'}
					<div class="rounded-[4px] border border-border">
						<div
							class="text-[var(--sb-text-faint)] border-b border-border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em]"
						>
							Roll back
						</div>
						<div class="px-3 py-2.5">
							<div class="text-muted-foreground pb-2 text-[11.5px]">
								This deployment's relations are still on disk, so it remains a rollback target
								until the janitor removes them.
							</div>
							<code
								class="block rounded-[3px] border border-border bg-[var(--sb-hover)] px-2 py-1.5 text-[11.5px]"
								>stb deployment rollback {detail.deploymentId}</code
							>
						</div>
					</div>
				{/if}

				{#if detail.state === 'staged'}
					<div class="rounded-[4px] border border-border">
						<div
							class="text-[var(--sb-text-faint)] border-b border-border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em]"
						>
							Promote
						</div>
						<div class="px-3 py-2.5">
							<div class="text-muted-foreground pb-2 text-[11.5px]">
								Models switch over one at a time, not all together. Promoting also releases
								{detail.wouldOrphan.relationCount} relation{detail.wouldOrphan.relationCount === 1
									? ''
									: 's'} ({formatBytes(detail.wouldOrphan.bytes)}).
							</div>
							<code
								class="block rounded-[3px] border border-border bg-[var(--sb-hover)] px-2 py-1.5 text-[11.5px]"
								>stb deployment promote {detail.deploymentId}</code
							>
						</div>
					</div>
				{/if}
			</div>
		</div>

		<table class="sb-list mt-4 w-full text-left">
			<thead>
				<tr class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]">
					<th class="px-3 py-2 font-normal">Model</th>
					<th class="px-3 py-2 font-normal">Live</th>
					<th class="px-3 py-2 font-normal">Staged</th>
					<th class="px-3 py-2 font-normal">Live rows</th>
					<th class="px-3 py-2 font-normal">Staged rows</th>
					<th class="px-3 py-2 font-normal">Delta</th>
				</tr>
			</thead>
			<tbody>
				{#each deploymentModels as model (model.logicalName)}
					<tr>
						<td class="code px-3 py-1.5 text-[12px]">{model.logicalName}</td>
						<td class="code text-[var(--sb-text-faint)] px-3 text-[11px]"
							>{suffixOf(model.liveRelation)}</td
						>
						<td class="code px-3 text-[11px]">{suffixOf(model.stagedRelation)}</td>
						<td class="code px-3 text-[11.5px]"
							>{model.liveRows === null ? '—' : formatInteger(model.liveRows)}</td
						>
						<td class="code px-3 text-[11.5px]">{formatInteger(model.stagedRows)}</td>
						<td class="code px-3 text-[11.5px]">
							{#if model.isNew}
								<span style:color="var(--sb-primary)">new</span>
							{:else}
								{@const delta = model.stagedRows - (model.liveRows ?? 0)}
								<span
									style:color={delta === 0 ? 'var(--sb-text-faint)' : 'var(--sb-secondary)'}
									>{delta >= 0 ? '+' : ''}{formatInteger(delta)}</span
								>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</div>
