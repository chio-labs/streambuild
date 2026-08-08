<script lang="ts">
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import { app } from '$lib/api/store.svelte';
	import { formatBytes, formatCompact } from '$lib/domain/format';
	import type { Deployment, DeploymentState } from '$lib/domain/types';

	// Deployments are grouped by lifecycle state rather than listed flat: the
	// question is always "what is live, what is waiting, what is dead weight",
	// and a single sorted table answers none of those.
	const SECTIONS: { state: DeploymentState; label: string; hint: string }[] = [
		{ state: 'active', label: 'Active', hint: 'serving the stable views' },
		{ state: 'staged', label: 'Staged', hint: 'built, awaiting promotion' },
		{ state: 'superseded', label: 'Superseded', hint: 'replaced, nothing points here' }
	];

	const PROBLEM_STATES: DeploymentState[] = [
		'incomplete',
		'metadata_missing',
		'physical_missing'
	];

	const deployments: Deployment[] = $derived(app.deployments);

	function inState(state: DeploymentState): Deployment[] {
		return deployments.filter((deployment) => deployment.state === state);
	}

	const problems: Deployment[] = $derived(
		deployments.filter((deployment) => PROBLEM_STATES.includes(deployment.state))
	);
	const supersededBytes: number = $derived(
		inState('superseded').reduce((total, deployment) => total + deployment.bytes, 0)
	);

	function shortId(deploymentId: string): string {
		return deploymentId.split('_').at(-1) ?? deploymentId;
	}
</script>

<AppTopbar title="Deployments" />

<div class="min-h-0 flex-1 overflow-y-auto px-[18px] py-4">
	{#if deployments.length === 0}
		<div class="text-muted-foreground rounded-md border border-[var(--sb-border)] p-6 text-[13px]">
			No deployments in this database. Virtual-mode pipelines create one on every build; a
			direct-mode project has none by design.
		</div>
	{:else}
		{#each SECTIONS as section (section.state)}
			{@const rows = inState(section.state)}
			{#if rows.length > 0}
				<div class="flex items-baseline gap-2 pb-1.5 pt-4 first:pt-0">
					<span
						class="font-mono text-[10px] uppercase tracking-[0.16em]"
						style:color={section.state === 'staged'
							? 'var(--sb-warn)'
							: section.state === 'active'
								? 'var(--sb-secondary)'
								: 'var(--sb-text-faint)'}>{section.label}</span
					>
					<span class="text-[var(--sb-text-faint)] text-[10.5px]">{section.hint}</span>
					{#if section.state === 'superseded'}
						<span class="text-[var(--sb-text-faint)] ml-auto code text-[10.5px]"
							>{rows.length} · {formatBytes(supersededBytes)} reclaimable</span
						>
					{/if}
				</div>

				<table class="sb-list w-full text-left">
					<tbody>
						{#each rows as deployment (deployment.deploymentId)}
							<tr>
								<td class="py-2 pr-3">
									<a
										href="/deployments/{deployment.deploymentId}"
										class="text-primary code text-[12.5px] font-medium hover:underline"
										>{deployment.deploymentId}</a
									>
									<div class="text-[var(--sb-text-faint)] code pt-0.5 text-[10.5px]">
										{deployment.rootNames.join(', ') || 'no recorded roots'}
									</div>
								</td>
								<td class="code px-3 text-[12px] whitespace-nowrap">
									{deployment.modelCount} model{deployment.modelCount === 1 ? '' : 's'}
									<div class="text-[var(--sb-text-faint)] pt-0.5 text-[10.5px]">
										{deployment.relationCount} relations
									</div>
								</td>
								<td class="code px-3 text-[12px] whitespace-nowrap">
									{formatCompact(deployment.rows)} rows
									<div class="text-[var(--sb-text-faint)] pt-0.5 text-[10.5px]">
										{formatBytes(deployment.bytes)}
									</div>
								</td>
								<td class="code px-3 text-[11.5px] whitespace-nowrap text-muted-foreground">
									{#if deployment.publishedAt}
										published {deployment.publishedAt.slice(0, 16)}
									{:else if deployment.createdAt}
										built {deployment.createdAt.slice(0, 16)}
									{:else}
										<span class="text-[var(--sb-text-faint)]">no timestamp</span>
									{/if}
								</td>
								<td class="px-3 pr-0 text-right whitespace-nowrap">
									{#if deployment.state === 'staged'}
										<a
											href="/deployments/{deployment.deploymentId}"
											class="sb-tag code hover:text-foreground"
											style:color="var(--sb-warn)">review · {shortId(deployment.deploymentId)}</a
										>
									{:else if deployment.state === 'active'}
										<span class="sb-tag code" style:color="var(--sb-secondary)">live</span>
									{:else}
										<span class="sb-tag code text-[var(--sb-text-faint)]">orphaned</span>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		{/each}

		{#if problems.length > 0}
			<div class="flex items-baseline gap-2 pb-1.5 pt-5">
				<span
					class="font-mono text-[10px] uppercase tracking-[0.16em]"
					style:color="var(--sb-error)">Needs attention</span
				>
				<span class="text-[var(--sb-text-faint)] text-[10.5px]">
					metadata and warehouse evidence disagree
				</span>
			</div>
			<table class="sb-list w-full text-left">
				<tbody>
					{#each problems as deployment (deployment.deploymentId)}
						<tr>
							<td class="code py-2 pr-3 text-[12.5px]">{deployment.deploymentId}</td>
							<td class="px-3">
								<span class="sb-tag code" style:color="var(--sb-error)">{deployment.state}</span>
							</td>
							<td class="text-muted-foreground px-3 text-[11.5px]">
								{deployment.missingRelationNames.length} missing relation{deployment
									.missingRelationNames.length === 1
									? ''
									: 's'}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	{/if}
</div>
