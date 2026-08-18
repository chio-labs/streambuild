<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left';
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw';
	import AppTopbar from '$lib/presentation/components/app-topbar.svelte';
	import LineageCanvas from '$lib/presentation/components/lineage/lineage-canvas.svelte';
	import SqlBlock from '$lib/presentation/components/sql-block.svelte';
	import { fetchRunStatement } from '$lib/api/main/build/fetch-run-statement';
	import { getProject } from '$lib/api/main/project/get-project';
	import { formatCompact } from '$lib/formatting/main/format-compact';
	import { formatDuration } from '$lib/formatting/main/format-duration';
	import { formatTimestamp } from '$lib/formatting/main/format-timestamp';
	import type { Project } from '$lib/domain/types';
	import { can } from '$lib/auth/main/can';
	import { canAnyPipeline } from '$lib/auth/main/can-any-pipeline';
	import { buildRunPresentation } from '$lib/run-presentation/main/build-run-presentation';
	import { createRunDetail } from '$lib/run-presentation/main/create-run-detail';
	import type { RunDetailController, RunPresentation } from '$lib/run-presentation/types';
	import type { RunEvent, RunStatement } from '$lib/api/types';

	const project: Project = getProject();
	const cancelAllowed = $derived(canAnyPipeline('build.cancel'));
	const killAllowed = $derived(can('build.kill'));
	const invocationId = $derived(page.params.id ?? '');
	const detail: RunDetailController = createRunDetail(
		async (nextInvocationId: string): Promise<void> => {
			await goto(`/runs/${nextInvocationId}?live=1`, { replaceState: true, noScroll: true });
		}
	);
	let expandedStatementSequence = $state<number | null>(null);
	let runStatements = $state<Record<number, RunStatement>>({});
	let statementLoading = $state<Set<number>>(new Set());
	let statementErrors = $state<Record<number, string>>({});

	async function toggleStatement(event: RunEvent): Promise<void> {
		const sequence: number | undefined = event.statementSequence;
		if (sequence === undefined) return;
		if (expandedStatementSequence === sequence) {
			expandedStatementSequence = null;
			return;
		}
		expandedStatementSequence = sequence;
		if (runStatements[sequence] || statementLoading.has(sequence)) return;
		const requestedInvocationId: string = invocationId;
		statementLoading = new Set(statementLoading).add(sequence);
		try {
			const statement: RunStatement = await fetchRunStatement(requestedInvocationId, sequence);
			if (invocationId !== requestedInvocationId) return;
			runStatements[sequence] = statement;
			runStatements = { ...runStatements };
		} catch (error) {
			if (invocationId !== requestedInvocationId) return;
			statementErrors[sequence] = String(error);
			statementErrors = { ...statementErrors };
		} finally {
			if (invocationId !== requestedInvocationId) return;
			const nextLoading: Set<number> = new Set(statementLoading);
			nextLoading.delete(sequence);
			statementLoading = nextLoading;
		}
	}

	$effect(() => {
		const id: string = invocationId;
		const live: boolean = page.url.searchParams.get('live') === '1';
		expandedStatementSequence = null;
		runStatements = {};
		statementLoading = new Set();
		statementErrors = {};
		detail.start(id, live);
		return (): void => detail.stop();
	});

	const presentation = $derived<RunPresentation>(
		buildRunPresentation({
			project,
			events: detail.view.events,
			running: detail.view.running,
			status: detail.view.status,
			commandLine: detail.view.commandLine,
			record: detail.view.record,
			nowMs: Date.now()
		})
	);
	const {
		running,
		status,
		stderr,
		ownedRunning,
		forceAvailable,
		signalling,
		lastSignalAgeSeconds,
		record,
		loadError,
		pollError,
		notFound,
		initialLoading
	} = $derived(detail.view);
	const {
		startedEvent,
		completedStatements,
		totalStatements,
		statementSummary,
		displayCommand,
		retryHref,
		outcome,
		outcomeColor,
		runGraph,
		mutedIds,
		notes,
		recordedScopeCount,
		missingScopeCount,
		timeline,
		eventLabels,
		durationSeconds
	} = $derived(presentation);
</script>

<AppTopbar title="Run" breadcrumb={`${project.name} / runs / ${invocationId.slice(0, 8)}`} />

<div class="flex min-h-0 flex-1 flex-col overflow-y-auto">
	{#if notFound}
		<div class="grid min-h-[320px] flex-1 place-items-center p-[18px]">
			<div class="max-w-md rounded-[4px] border border-border p-5 text-center">
				<div class="font-display text-[16px] font-semibold">Run not found</div>
				<p class="text-muted-foreground pt-2 font-mono text-[11.5px]">
					No durable run or active local process matches <code class="code">{invocationId}</code>.
				</p>
				<a href="/runs" class="text-primary mt-3 inline-block font-mono text-[11px] hover:underline">
					Back to runs
				</a>
			</div>
		</div>
	{:else if initialLoading}
		<div class="flex min-h-[520px] flex-1 flex-col" aria-label="Loading run details">
			<div class="flex h-[53px] shrink-0 items-center gap-3 border-b border-border px-[18px]">
				<div class="h-5 w-16 animate-pulse rounded bg-[var(--sb-inset)]"></div>
				<div class="h-6 w-24 animate-pulse rounded-full bg-[var(--sb-inset)]"></div>
				<div class="h-7 min-w-0 flex-1 animate-pulse rounded bg-[var(--sb-inset)]"></div>
			</div>
			<div class="grid h-[380px] shrink-0 place-items-center border-b border-border">
				<span class="text-muted-foreground font-mono text-[11px]">loading run timeline…</span>
			</div>
			<div class="m-[18px] h-24 animate-pulse rounded-[4px] border border-border bg-[var(--sb-inset)]/40"></div>
		</div>
	{:else}
	<!-- header -->
	<div class="flex shrink-0 flex-wrap items-center gap-3 border-b border-border px-[18px] py-3">
		<a href="/runs" class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 font-mono text-[11px]">
			<ArrowLeftIcon size={12} /> runs
		</a>
		<span
			class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10.5px]"
			style:border-color="color-mix(in srgb, {outcomeColor} 40%, var(--border))"
			style:color={outcomeColor}
		>
			<span
				class="h-1.5 w-1.5 rounded-full {outcome === 'running' ? 'animate-pulse' : ''}"
				style:background={outcomeColor}
			></span>
			{outcome}
		</span>
		<code class="code max-w-full break-all text-[11px]" aria-label="Run ID" title={invocationId}
			>{invocationId}</code
		>
		<code
			class="bg-[var(--sb-inset)] min-w-0 flex-1 truncate rounded-[4px] border border-border px-2.5 py-1 font-mono text-[11px]"
			>$ {displayCommand}</code
		>
		<span class="text-muted-foreground shrink-0 font-mono text-[11px]">
			{#if durationSeconds !== null}{formatDuration(durationSeconds)}{/if}
			{#if statementSummary !== null}
				· {statementSummary} statements
			{/if}
		</span>
		{#if retryHref}
			<a
				href={retryHref}
				class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded border border-border px-2.5 py-1 font-mono text-[10.5px]"
			>
				<RotateCcwIcon size={11} /> Open in Plan
			</a>
		{/if}
		{#if ownedRunning && running}
			<button
				class="rounded border border-border px-2.5 py-1 font-mono text-[10.5px] text-[var(--sb-warning)]"
				disabled={signalling || !cancelAllowed}
				title={cancelAllowed ? undefined : 'Requires the build.cancel permission'}
				onclick={() => void detail.requestCancel()}>Cancel</button
			>
		{/if}
		{#if running && !ownedRunning}
			<span class="text-[var(--sb-text-faint)] font-mono text-[10px]">
				This server does not own the process and cannot cancel it.
			</span>
		{/if}
		{#if forceAvailable}
			<button
				class="rounded border px-2.5 py-1 font-mono text-[10.5px]"
				style:color="var(--sb-error)"
				disabled={signalling || !killAllowed}
				title={killAllowed ? undefined : 'Requires the target-scoped build.kill permission'}
				onclick={() => void detail.requestKill()}>Force kill</button
			>
		{/if}
	</div>
	{#if status === 'unresponsive' || status === 'presumed_failed'}
		<div class="border-b border-border px-[18px] py-2 font-mono text-[11px]" style:color="var(--sb-warning)">
			{status === 'presumed_failed' ? 'Presumed failed' : 'Unresponsive'} — no signal for
			{lastSignalAgeSeconds ?? 0}s. Last activity: {record?.lastActivity ?? 'unknown'}.
			The process may recover; rerunning the build is safe once it is presumed failed.
			{#if status === 'presumed_failed' && retryHref}
				<a href={retryHref} class="pl-2 underline">Rerun from Plan</a>
			{/if}
		</div>
	{/if}

	{#if loadError}
		<div class="border-b border-border px-[18px] py-2">
			<p class="font-mono text-[12px]" style:color="var(--sb-error)">{loadError}</p>
		</div>
	{/if}
	{#if pollError}
		<div class="border-b border-border px-[18px] py-2 font-mono text-[11px]" style:color="var(--sb-warning)">
			Observability temporarily unavailable: {pollError}. Retrying…
		</div>
	{/if}
		<!-- progress -->
		{#if totalStatements !== null && totalStatements > 0}
			<div class="shrink-0 px-[18px] pt-3">
				<div class="h-[4px] w-full overflow-hidden rounded-full bg-[var(--sb-inset)]">
					<div
						class="h-full rounded-full transition-all"
						style:width="{Math.min((completedStatements.length / totalStatements) * 100, 100)}%"
						style:background={outcomeColor}
					></div>
				</div>
			</div>
		{/if}

		<!-- the pipeline, growing as replays land -->
		<div class="h-[380px] shrink-0 border-b border-border">
			{#if runGraph.nodes.length > 0}
				<div class="flex h-full flex-col">
					{#if missingScopeCount > 0}
						<div class="border-b border-border px-3 py-1.5 font-mono text-[10.5px] text-[var(--sb-warning)]">
							{missingScopeCount} recorded scope {missingScopeCount === 1 ? 'node is' : 'nodes are'} no longer present in the current project.
						</div>
					{/if}
					<div class="min-h-0 flex-1">
						<LineageCanvas
							{project}
							graph={runGraph}
							{mutedIds}
							{notes}
							groupMode="none"
							compactNodes
							embedded
						/>
					</div>
				</div>
			{:else if startedEvent === undefined && ownedRunning}
				<div class="text-muted-foreground grid h-full place-items-center px-6 text-center font-mono text-[11px]">
					Compiling project and inspecting warehouse…
				</div>
			{:else if recordedScopeCount > 0}
				<div class="text-muted-foreground grid h-full place-items-center px-6 text-center font-mono text-[11px]">
					The recorded scope no longer exists in the current project.
				</div>
			{:else}
				<div class="text-muted-foreground grid h-full place-items-center px-6 text-center font-mono text-[11px]">
					Scope was not recorded for this run. Project-wide lineage is intentionally not shown.
				</div>
			{/if}
		</div>

		{#if stderr && outcome === 'failed'}
			<div class="shrink-0 px-[18px] pt-3">
				<pre
					class="max-h-[200px] overflow-auto rounded-[4px] border p-3 font-mono text-[11px]"
					style:border-color="color-mix(in srgb, var(--sb-error) 45%, var(--border))">{stderr}</pre>
			</div>
		{/if}

		<!-- event timeline -->
		<div class="min-h-0 flex-1 p-[18px]">
			<div
				class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
			>
				Events {#if running}<span class="text-[var(--sb-secondary)]">· live</span>{/if}
			</div>
			<div class="overflow-hidden rounded-[4px] border border-border">
				{#if timeline.length === 0 && ownedRunning}
					<div class="flex items-center gap-3 px-3 py-1.5">
						<span class="text-[var(--sb-text-faint)] w-[86px] shrink-0 font-mono text-[10.5px]">now</span>
						<span class="w-[92px] shrink-0"><span class="sb-tag code">startup</span></span>
						<span class="code min-w-0 flex-1 text-[11.5px]">Compile project and inspect warehouse</span>
					</div>
				{/if}
				{#each timeline as event (event.sequence)}
					<div class="border-b border-[var(--border-subtle)] last:border-b-0">
						<button
							type="button"
							data-statement-sequence={event.statementSequence}
							aria-expanded={event.statementSequence === undefined
								? undefined
								: expandedStatementSequence === event.statementSequence}
							title={event.statementSequence === undefined ? undefined : 'Show executed SQL'}
							class="flex w-full items-center gap-3 px-3 py-1.5 text-left {event.statementSequence ===
							undefined
								? 'cursor-default'
								: 'hover:bg-[var(--sb-hover)]'}"
							onclick={() => void toggleStatement(event)}
						>
						<span class="text-[var(--sb-text-faint)] w-[86px] shrink-0 font-mono text-[10.5px]"
							>{formatTimestamp(event.emittedAt).slice(11)}</span
						>
						<span class="w-[92px] shrink-0">
							{#if event.phase}
								<span class="sb-tag code">{event.phase}</span>
							{:else}
								<span
									class="sb-tag code"
									style:color={event.event === 'run_completed'
										? outcomeColor
										: 'var(--sb-secondary)'}>{event.event.replace('_', ' ')}</span
								>
							{/if}
						</span>
						<span
							class="code min-w-0 flex-1 truncate text-[11.5px]"
							title={event.stepId ?? undefined}>{eventLabels.get(event.sequence)}</span
						>
						{#if event.errorMessage}
							<span
								class="max-w-[320px] shrink-0 truncate font-mono text-[10.5px]"
								style:color="var(--sb-error)"
								title={event.errorMessage}>{event.errorMessage}</span
							>
						{/if}
						{#if event.writtenRows !== null && event.writtenRows !== undefined}
							<span class="shrink-0 font-mono text-[10.5px]" style:color="var(--sb-secondary)"
								>{formatCompact(event.writtenRows)} rows</span
							>
						{/if}
						{#if event.elapsedMs !== undefined}
							<span class="text-[var(--sb-text-faint)] w-[64px] shrink-0 text-right font-mono text-[10.5px]"
								>{event.elapsedMs} ms</span
							>
						{/if}
						{#if event.statementSequence !== undefined}
							<ChevronDownIcon
								size={13}
								class="text-muted-foreground shrink-0 transition-transform {expandedStatementSequence ===
								event.statementSequence
									? 'rotate-180'
									: ''}"
							/>
						{/if}
						</button>
						{#if event.statementSequence !== undefined && expandedStatementSequence === event.statementSequence}
							<div class="border-t border-[var(--border-subtle)] bg-[var(--sb-surface-low)] p-3">
								{#if statementLoading.has(event.statementSequence)}
									<div class="text-muted-foreground font-mono text-[11px]">loading SQL…</div>
								{:else if statementErrors[event.statementSequence]}
									<div class="font-mono text-[11px]" style:color="var(--sb-error)">
										{statementErrors[event.statementSequence]}
									</div>
								{:else if runStatements[event.statementSequence]?.found && runStatements[event.statementSequence]?.sql}
									<SqlBlock
										artifacts={[{ label: 'executed', code: runStatements[event.statementSequence].sql ?? null }]}
										maxHeight="420px"
										caption={`statement ${event.statementSequence} · ${event.stepId ?? ''}`}
									/>
								{:else}
									<div class="text-muted-foreground font-mono text-[11px]">
										SQL was not recorded for this run.
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>
