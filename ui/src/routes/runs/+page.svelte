<script lang="ts">
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import { getProject, fetchRuns, type RunRecord } from '$lib/api';
	import { formatAgo, formatDuration, formatTimestamp } from '$lib/domain/format';
	import type { Project } from '$lib/domain/types';

	const project: Project = getProject();

	// Recorded CLI invocation history from `_streambuild_invocations` — facts
	// about what already ran, not a scheduler. Loaded once per visit; a run
	// happens out-of-band in a shell, so there is nothing to poll for here.
	let runs = $state<RunRecord[] | null>(null);
	let loadError = $state<string | null>(null);

	$effect(() => {
		fetchRuns()
			.then((records) => {
				runs = records;
				loadError = null;
			})
			.catch((error: Error) => {
				loadError = error.message;
			});
	});

	function outcomeColor(outcome: string): string {
		if (outcome === 'succeeded') return 'var(--sb-success)';
		if (outcome === 'failed') return 'var(--sb-error)';
		return 'var(--sb-warning)';
	}
</script>

<AppTopbar title="Runs" />

<div class="min-h-0 flex-1 overflow-y-auto">
	{#if loadError}
		<div class="p-[18px]">
			<p class="font-mono text-[12px]" style:color="var(--sb-error)">{loadError}</p>
		</div>
	{:else if runs === null}
		<div class="text-muted-foreground p-[18px] font-mono text-[12px]">loading run history…</div>
	{:else if runs.length === 0}
		<div class="p-[18px]">
			<p class="text-muted-foreground text-[13px]">
				No recorded runs. History appears after the first <code class="code text-[12px]"
					>stb build</code
				> against this database.
			</p>
		</div>
	{:else}
		<table class="sb-list w-full text-left">
			<thead>
				<tr>
					<th class="px-[18px] py-2 font-normal">Outcome</th>
					<th class="px-3 py-2 font-normal">Command</th>
					<th class="px-3 py-2 font-normal">Mode</th>
					<th class="px-3 py-2 font-normal">Nodes</th>
					<th class="px-3 py-2 font-normal">Duration</th>
					<th class="px-3 py-2 font-normal">Started</th>
					<th class="px-3 py-2 pr-[18px] font-normal">Version</th>
				</tr>
			</thead>
			<tbody>
				{#each runs as run (run.invocationId)}
					<tr>
						<td class="px-[18px] py-2">
							<span class="flex items-center gap-2">
								<span
									class="h-1.5 w-1.5 shrink-0 rounded-[2px]"
									style:background={outcomeColor(run.outcome)}
								></span>
								<span class="font-mono text-[11.5px]">{run.outcome}</span>
							</span>
							{#if run.errorMessage}
								<div
									class="max-w-[420px] truncate pt-1 font-mono text-[10.5px]"
									style:color="var(--sb-error)"
									title={run.errorMessage}
								>
									{run.errorMessage}
								</div>
							{/if}
						</td>
						<td class="code px-3 text-[12px]">stb {run.command}</td>
						<td class="px-3"><span class="sb-tag code">{run.mode}</span></td>
						<td class="text-muted-foreground code px-3 text-[11.5px]"
							>{run.selectedNodeCount}</td
						>
						<td class="text-muted-foreground code px-3 text-[11.5px]"
							>{formatDuration(run.durationMs / 1000)}</td
						>
						<td class="text-muted-foreground code px-3 text-[11.5px]"
							title={formatTimestamp(run.startedAt)}
							>{formatAgo(run.startedAt, project.capturedAt)}</td
						>
						<td class="text-muted-foreground code px-3 pr-[18px] text-[11.5px]"
							>{run.toolVersion}</td
						>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</div>
