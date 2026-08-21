<script lang="ts">
	import ClockIcon from '@lucide/svelte/icons/clock-3';
	import AppTopbar from '$lib/presentation/components/app-topbar.svelte';
	import ErrorPreview from '$lib/presentation/components/error-preview.svelte';
	import { cancelBuild } from '$lib/api/main/build/cancel-build';
	import { fetchBuildFeed } from '$lib/api/main/build/fetch-build-feed';
	import { getProject } from '$lib/api/main/project/get-project';
	import { fetchRuns } from '$lib/api/main/runs/fetch-runs';
	import type { RunRecord } from '$lib/api/types';
	import { formatAgo } from '$lib/formatting/main/format-ago';
	import { formatDuration } from '$lib/formatting/main/format-duration';
	import { formatTimestamp } from '$lib/formatting/main/format-timestamp';
	import type { Project } from '$lib/domain/types';
	import { canAnyPipeline } from '$lib/auth/main/can-any-pipeline';
	import { createAuditSchedulerState } from '$lib/quality-monitoring/main/create-audit-scheduler-state.svelte';
	import { runsInScope, type RunScope } from '$lib/run-presentation/main/runs-in-scope';
	import { scheduledAuditRuns } from '$lib/run-presentation/main/scheduled-audit-runs';

	const project: Project = getProject();
	const cancelAllowed = $derived(canAnyPipeline('build.cancel'));
	const scheduler = createAuditSchedulerState();

	// Recorded CLI invocation history from `_streambuild_invocations`. Runs
	// happen out-of-band in a shell, so poll while the page is visible — a
	// build finished in another terminal should appear without re-navigating.
	let runs = $state<RunRecord[] | null>(null);
	let loadError = $state<string | null>(null);
	let ownedInvocationId = $state<string | null>(null);
	let cancellingInvocationId = $state<string | null>(null);

	const POLL_MS = 10_000;

	async function refresh(): Promise<void> {
		try {
			const runsRequest: Promise<RunRecord[]> = fetchRuns().then((recordedRuns) => {
				runs = recordedRuns;
				return recordedRuns;
			});
			const [, ownership] = await Promise.all([runsRequest, fetchBuildFeed(0)]);
			ownedInvocationId = ownership.running ? ownership.invocationId : null;
			loadError = null;
		} catch (error) {
			loadError = (error as Error).message;
		}
	}

	async function cancelOwned(invocationId: string): Promise<void> {
		if (!window.confirm('Cancel this build? A direct closure may be partially rebuilt; rerunning is safe.')) return;
		if (cancellingInvocationId !== null) return;
		cancellingInvocationId = invocationId;
		try {
			await cancelBuild(invocationId);
			await refresh();
		} catch (error) {
			loadError = error instanceof Error ? error.message : String(error);
		} finally {
			cancellingInvocationId = null;
		}
	}

	$effect(() => {
		const stopScheduler: () => void = scheduler.start();
		refresh();
		const timer: ReturnType<typeof setInterval> = setInterval(() => {
			if (!document.hidden) refresh();
		}, POLL_MS);
		return () => {
			clearInterval(timer);
			stopScheduler();
		};
	});

	let scope = $state<RunScope>('builds');
	type StatusFilter = 'all' | 'succeeded' | 'failed';
	let statusFilter = $state<StatusFilter>('all');

	const scopedRuns = $derived(runsInScope(runs ?? [], scope));
	const auditCycles = $derived(scheduledAuditRuns(runs ?? []));
	const latestAuditCycle = $derived(auditCycles[0] ?? null);
	const automationDisplay = $derived.by(() => {
		const payload: typeof scheduler.payload = scheduler.payload;
		if (!payload) return null;
		if (!payload.enabled) return { label: 'Disabled', color: 'var(--sb-text-faint)' };
		if (payload.health.state === 'backing_off') return { label: 'Retrying', color: 'var(--sb-warning)' };
		if (payload.state === 'blocked' || payload.health.state === 'blocked') {
			return { label: 'Paused', color: 'var(--sb-warning)' };
		}
		if (payload.health.runningAuditCount) return { label: 'Running', color: 'var(--sb-secondary)' };
		return { label: 'Active', color: 'var(--sb-success)' };
	});
	const succeededCount = $derived(scopedRuns.filter((run) => run.status === 'succeeded').length);
	const failedCount = $derived(
		scopedRuns.filter((run) => run.status === 'failed' || run.status === 'presumed_failed').length
	);

	const visibleRuns = $derived(
		scopedRuns.filter((run) => {
			if (statusFilter === 'all') return true;
			if (statusFilter === 'succeeded') return run.status === 'succeeded';
			return run.status === 'failed' || run.status === 'presumed_failed';
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
		if (outcome === 'running') {
			return { label: 'Running', dot: 'var(--sb-secondary)', text: 'var(--sb-secondary)', border: 'var(--border)' };
		}
		if (outcome === 'unresponsive') {
			return { label: 'Unresponsive', dot: 'var(--sb-warning)', text: 'var(--sb-warning)', border: 'var(--border)' };
		}
		if (outcome === 'presumed_failed') {
			return { label: 'Presumed failed', dot: 'var(--sb-warning)', text: 'var(--sb-warning)', border: 'var(--border)' };
		}
		return {
			label: outcome,
			dot: 'var(--sb-warning)',
			text: 'var(--sb-warning)',
			border: 'color-mix(in srgb, var(--sb-warning) 40%, var(--border))'
		};
	}

	const TAB_DEFS: { key: StatusFilter; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'succeeded', label: 'Succeeded' },
		{ key: 'failed', label: 'Failed' }
	];

	function tabCount(key: StatusFilter): number | null {
		if (runs === null) return null;
		if (key === 'all') return scopedRuns.length;
		if (key === 'succeeded') return succeededCount;
		return failedCount;
	}

	const SCOPE_DEFS: { key: RunScope; label: string }[] = [
		{ key: 'builds', label: 'Builds' },
		{ key: 'other', label: 'Other operations' },
		{ key: 'all', label: 'All history' }
	];

	function scopeCount(key: RunScope): number | null {
		return runs === null ? null : runsInScope(runs, key).length;
	}
</script>

<AppTopbar title="Runs" />

<div class="flex min-h-0 flex-1 flex-col">
	<a
		href="/quality"
		class="hover:bg-[var(--sb-hover)] mx-[18px] mt-[18px] flex shrink-0 items-center gap-3 rounded-[4px] border border-border bg-[var(--sidebar-accent)]/20 px-3 py-2.5 transition-colors"
	>
		<ClockIcon size={13} class="text-muted-foreground" />
		<div class="min-w-0">
			<div class="flex items-baseline gap-2">
				<span class="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--sb-text-faint)]">
					Audit automation
				</span>
				{#if automationDisplay}
					<span class="text-xs" style:color={automationDisplay.color}>
						{automationDisplay.label}
					</span>
				{:else if scheduler.loading}
					<span class="text-muted-foreground text-xs">Loading…</span>
				{:else}
					<span class="text-xs" style:color="var(--sb-error)">Unavailable</span>
				{/if}
			</div>
			<div class="text-[var(--sb-text-faint)] mt-0.5 truncate font-mono text-[10px]">
				{#if latestAuditCycle?.auditSummary}
					Latest cycle: {latestAuditCycle.auditSummary.passed}/{latestAuditCycle.auditSummary.total} passed
					{#if latestAuditCycle.auditSummary.warning} · {latestAuditCycle.auditSummary.warning} warning{/if}
					{#if latestAuditCycle.auditSummary.failed} · {latestAuditCycle.auditSummary.failed} failed{/if}
					{#if latestAuditCycle.auditSummary.error} · {latestAuditCycle.auditSummary.error} errors{/if}
				{:else if latestAuditCycle}
					Latest cycle {formatAgo(latestAuditCycle.startedAt, project.capturedAt)}
				{:else}
					Scheduled audit cycles are managed in Quality
				{/if}
			</div>
		</div>
		<span class="text-primary ml-auto hidden font-mono text-[10.5px] sm:block">Open Quality →</span>
	</a>

	<div class="mt-3 flex shrink-0 items-center gap-1 overflow-x-auto border-b border-border px-[18px]">
		{#each SCOPE_DEFS as item (item.key)}
			<button
				class="relative shrink-0 px-3 py-2.5 text-[12.5px] transition-colors {scope === item.key
					? 'text-foreground after:absolute after:inset-x-2 after:bottom-0 after:h-[2px] after:rounded-t after:bg-primary after:content-[\'\']'
					: 'text-muted-foreground hover:text-foreground'}"
				onclick={() => (scope = item.key)}
			>
				{item.label}
				{#if scopeCount(item.key) !== null}
					<span class="pl-1 font-mono text-[10.5px] text-[var(--sb-text-faint)]">{scopeCount(item.key)}</span>
				{/if}
			</button>
		{/each}
		<div class="ml-auto flex shrink-0 items-center gap-1">
			{#each TAB_DEFS as tab (tab.key)}
				<button
					class="rounded-[4px] px-2 py-1 font-mono text-[10.5px] transition-colors {statusFilter === tab.key
						? 'bg-[var(--sidebar-accent)] text-foreground'
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
						No {statusFilter === 'all' ? '' : `${statusFilter} `}{scope === 'builds' ? 'builds' : scope === 'other' ? 'other operations' : 'runs'}.
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
						<th class="w-[220px] px-3 py-2 font-normal sm:px-[18px]">ID</th>
						<th class="hidden px-3 py-2 font-normal md:table-cell">Command</th>
						<th class="px-2 py-2 font-normal sm:px-3">Status</th>
						<th class="hidden px-3 py-2 font-normal lg:table-cell">Created at</th>
						<th class="hidden px-3 py-2 pr-[18px] text-right font-normal xl:table-cell">Duration</th>
					</tr>
				</thead>
				<tbody>
					{#each visibleRuns as run (run.invocationId)}
						{@const chip = statusChip(run.status)}
						<tr>
							<td class="w-[220px] px-3 py-2.5 align-top sm:px-[18px]">
								<a
									href="/runs/{run.invocationId}"
									class="code text-primary text-[12px] hover:underline"
									title={run.invocationId}>{run.invocationId.slice(0, 8)}</a
								>
								<div class="flex max-w-[190px] flex-wrap items-center gap-1.5 pt-1 sm:max-w-none">
									<span class="sb-tag code">{run.mode}</span>
									<span class="sb-tag code">{run.selectedNodeCount} nodes</span>
									{#if run.toolVersion}<span class="sb-tag code">v{run.toolVersion}</span>{/if}
								</div>
							</td>
							<td class="hidden px-3 align-top md:table-cell">
								<div class="code pt-0.5 text-[12px]">
									{run.displayCommand?.startsWith('stb ')
										? run.displayCommand
										: `stb ${run.displayCommand ?? run.command}`}
								</div>
								{#if run.errorMessage}
									<ErrorPreview
										text={run.errorMessage}
										title="Run error"
										subtitle={`${run.command} · ${run.invocationId}`}
										class="max-w-[480px] pt-1"
									/>
								{/if}
							</td>
							<td class="px-2 align-top sm:px-3">
								<span
									class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10.5px]"
									style:border-color={chip.border}
									style:color={chip.text}
								>
									<span class="h-1.5 w-1.5 rounded-full" style:background={chip.dot}></span>
									{chip.label}
								</span>
								{#if run.totalStatements !== null && run.completedOperationCount !== null}
									<div class="text-[var(--sb-text-faint)] pt-1 font-mono text-[10px]">
										{run.completedOperationCount}/{run.totalStatements}
										{run.command === 'audit' ? 'audits' : 'statements'}
										{#if run.currentStep} · {run.currentStep}{/if}
									</div>
								{/if}
								{#if run.status === 'unresponsive' || run.status === 'presumed_failed'}
									<div class="text-[var(--sb-text-faint)] pt-1 font-mono text-[10px]">
										no signal for {run.lastSignalAgeSeconds}s
										{#if run.currentStep === null} · last activity {run.lastActivity ?? 'unknown'}{/if}
									</div>
									{#if run.status === 'presumed_failed'}
										<div class="text-[var(--sb-text-faint)] pt-1 text-[10px]">The process may have been killed. Rerunning is safe.</div>
									{/if}
								{/if}
								{#if ownedInvocationId === run.invocationId && run.status === 'running'}
									<button class="mt-1 font-mono text-[10px] underline disabled:opacity-50" style:color="var(--sb-warning)" disabled={cancellingInvocationId !== null || !cancelAllowed} title={cancelAllowed ? undefined : 'Requires the build.cancel permission'} onclick={() => void cancelOwned(run.invocationId)}>{cancellingInvocationId === run.invocationId ? 'Cancelling...' : 'Cancel'}</button>
								{/if}
							</td>
							<td class="hidden px-3 align-top lg:table-cell">
								<div class="text-[12px]">{formatTimestamp(run.startedAt)}</div>
								<div class="text-[var(--sb-text-faint)] font-mono text-[10.5px]">
									{formatAgo(run.startedAt, project.capturedAt)}
								</div>
							</td>
							<td
								class="text-muted-foreground code hidden px-3 pr-[18px] pt-3 text-right align-top text-[11.5px] xl:table-cell"
								>{formatDuration(run.durationMs / 1000)}</td
							>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>
