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

	// Dagster-style status tabs: the one filter everyone reaches for first.
	type StatusFilter = 'all' | 'succeeded' | 'failed';
	let statusFilter = $state<StatusFilter>('all');

	const succeededCount = $derived((runs ?? []).filter((run) => run.outcome === 'succeeded').length);
	const failedCount = $derived((runs ?? []).filter((run) => run.outcome !== 'succeeded').length);

	const visibleRuns = $derived(
		(runs ?? []).filter((run) => {
			if (statusFilter === 'all') return true;
			if (statusFilter === 'succeeded') return run.outcome === 'succeeded';
			return run.outcome !== 'succeeded';
		})
	);

	type Chip = { label: string; dot: string; text: string; border: string };

	function statusChip(outcome: string): Chip {
		if (outcome === 'succeeded') {
			return {
				label: 'Success',
				dot: 'var(--sb-success)',
				text: 'var(--sb-success)',
				border: 'color-mix(in srgb, var(--sb-success) 40%, var(--border))'
			};
		}
		if (outcome === 'failed') {
			return {
				label: 'Failure',
				dot: 'var(--sb-error)',
				text: 'var(--sb-error)',
				border: 'color-mix(in srgb, var(--sb-error) 40%, var(--border))'
			};
		}
		return {
			label: outcome,
			dot: 'var(--sb-warning)',
			text: 'var(--sb-warning)',
			border: 'color-mix(in srgb, var(--sb-warning) 40%, var(--border))'
		};
	}

	const TAB_DEFS: { key: StatusFilter; label: string }[] = [
		{ key: 'all', label: 'All runs' },
		{ key: 'succeeded', label: 'Succeeded' },
		{ key: 'failed', label: 'Failed' }
	];

	function tabCount(key: StatusFilter): number | null {
		if (runs === null) return null;
		if (key === 'all') return runs.length;
		if (key === 'succeeded') return succeededCount;
		return failedCount;
	}
</script>

<AppTopbar title="Runs" />

<div class="flex min-h-0 flex-1 flex-col">
	<!-- status tabs, dagster-style -->
	<div class="flex shrink-0 items-center gap-1 border-b border-border px-[18px]">
		{#each TAB_DEFS as tab (tab.key)}
			<button
				class="relative px-3 py-2.5 text-[12.5px] transition-colors {statusFilter === tab.key
					? 'text-foreground after:absolute after:inset-x-2 after:bottom-0 after:h-[2px] after:rounded-t after:bg-primary after:content-[\'\']'
					: 'text-muted-foreground hover:text-foreground'}"
				onclick={() => (statusFilter = tab.key)}
			>
				{tab.label}
				{#if tabCount(tab.key) !== null}
					<span class="text-[var(--sb-text-faint)] pl-1 font-mono text-[10.5px]"
						>{tabCount(tab.key)}</span
					>
				{/if}
			</button>
		{/each}
	</div>

	<div class="min-h-0 flex-1 overflow-y-auto">
		{#if loadError}
			<div class="p-[18px]">
				<p class="font-mono text-[12px]" style:color="var(--sb-error)">{loadError}</p>
			</div>
		{:else if runs === null}
			<div class="text-muted-foreground p-[18px] font-mono text-[12px]">loading run history…</div>
		{:else if visibleRuns.length === 0}
			<div class="p-[18px]">
				<p class="text-muted-foreground text-[13px]">
					{#if runs.length === 0}
						No recorded runs. History appears after the first
						<code class="code text-[12px]">stb build</code> against this database.
					{:else}
						No {statusFilter} runs.
					{/if}
				</p>
			</div>
		{:else}
			<!-- Column set follows Dagster's runs table (ID+tags / target / status /
			     created / duration), except the selection column is named Command:
			     "target" already means the dev/prod profile in StreamBuild. -->
			<table class="sb-list w-full text-left">
				<thead>
					<tr>
						<th class="px-[18px] py-2 font-normal">ID</th>
						<th class="px-3 py-2 font-normal">Command</th>
						<th class="px-3 py-2 font-normal">Status</th>
						<th class="px-3 py-2 font-normal">Created at</th>
						<th class="px-3 py-2 pr-[18px] text-right font-normal">Duration</th>
					</tr>
				</thead>
				<tbody>
					{#each visibleRuns as run (run.invocationId)}
						{@const chip = statusChip(run.outcome)}
						<tr>
							<td class="px-[18px] py-2.5 align-top">
								<a
									href="/runs/{run.invocationId}"
									class="code text-primary text-[12px] hover:underline"
									title={run.invocationId}>{run.invocationId.slice(0, 8)}</a
								>
								<div class="flex items-center gap-1.5 pt-1">
									<span class="sb-tag code">{run.mode}</span>
									<span class="sb-tag code">{run.selectedNodeCount} nodes</span>
									<span class="sb-tag code">v{run.toolVersion}</span>
								</div>
							</td>
							<td class="px-3 align-top">
								<div class="code pt-0.5 text-[12px]">stb {run.command}</div>
								{#if run.errorMessage}
									<div
										class="max-w-[480px] truncate pt-1 font-mono text-[10.5px]"
										style:color="var(--sb-error)"
										title={run.errorMessage}
									>
										{run.errorMessage}
									</div>
								{/if}
							</td>
							<td class="px-3 align-top">
								<span
									class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10.5px]"
									style:border-color={chip.border}
									style:color={chip.text}
								>
									<span class="h-1.5 w-1.5 rounded-full" style:background={chip.dot}></span>
									{chip.label}
								</span>
							</td>
							<td class="px-3 align-top">
								<div class="text-[12px]">{formatTimestamp(run.startedAt)}</div>
								<div class="text-[var(--sb-text-faint)] font-mono text-[10.5px]">
									{formatAgo(run.startedAt, project.capturedAt)}
								</div>
							</td>
							<td
								class="text-muted-foreground code px-3 pr-[18px] pt-3 text-right align-top text-[11.5px]"
								>{formatDuration(run.durationMs / 1000)}</td
							>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>
