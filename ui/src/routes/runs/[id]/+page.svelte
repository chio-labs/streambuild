<script lang="ts">
	import { page } from '$app/state';
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import LineageCanvas from '$lib/components/lineage/lineage-canvas.svelte';
	import {
		getProject,
		cancelBuild,
		killBuild,
		fetchBuildFeed,
		fetchRunEvents,
		fetchRuns,
		type RunEvent,
		type RunRecord,
		type RunStatus
	} from '$lib/api';
	import { refreshLiveState } from '$lib/api/store.svelte';
	import { buildLogicalGraph } from '$lib/domain/derive';
	import { formatCompact, formatDuration, formatTimestamp } from '$lib/domain/format';
	import type { Graph, Project } from '$lib/domain/types';

	const project: Project = getProject();
	const invocationId = $derived(page.params.id ?? '');

	let events = $state<RunEvent[]>([]);
	let running = $state<boolean>(true);
	let status = $state<RunStatus>('running');
	let exitCode = $state<number | null>(null);
	let stderr = $state<string>('');
	let owned = $state<boolean>(false);
	let ownedRunning = $state<boolean>(false);
	let forceAvailable = $state<boolean>(false);
	let signalling = $state<boolean>(false);
	let lastSignalAgeSeconds = $state<number | null>(null);
	let record = $state<RunRecord | null>(null);
	let commandLine = $state<string>('build');
	let loadError = $state<string | null>(null);
	let notFound = $state<boolean>(false);

	const POLL_MS: number = 1200;

	$effect(() => {
		const id: string = invocationId;
		events = [];
		record = null;
		stderr = '';
		owned = false;
		ownedRunning = false;
		notFound = false;
		let cancelled: boolean = false;
		let timer: ReturnType<typeof setTimeout> | null = null;
		let cursor: number = 0;

		async function pollDurable(): Promise<void> {
			try {
				const feed = await fetchRunEvents(id, cursor);
				if (cancelled) return;
				if (feed.events.length > 0) cursor = feed.events[feed.events.length - 1].sequence;
				const combinedEvents = [...events, ...feed.events];
				const runStarted = combinedEvents.find((event) => event.event === 'run_started');
				const recentEvents = combinedEvents.slice(-399);
				events = runStarted !== undefined && !recentEvents.includes(runStarted)
					? [runStarted, ...recentEvents]
					: recentEvents;
				status = feed.status ?? 'running';
				lastSignalAgeSeconds = feed.lastSignalAgeSeconds;
				running = status === 'running' || status === 'unresponsive';
				const ownership = await fetchBuildFeed(0);
				if (cancelled) return;
				owned = ownership.invocationId === id;
				ownedRunning = owned && ownership.running;
				if (owned) {
					stderr = ownership.stderr;
					forceAvailable = ownership.forceAvailable;
				}
				const loadedRecord = await loadRunRecord();
				if (cancelled) return;
				if (!feed.found && !owned && loadedRecord === null) {
					notFound = true;
					running = false;
					loadError = null;
					return;
				}
				notFound = false;
				record = loadedRecord;
				if (record !== null) {
					exitCode = record.exitCode;
					commandLine = record.command;
					status = record.status;
				}
				loadError = null;
				if (running || feed.hasMore) {
					timer = setTimeout(() => void pollDurable(), feed.hasMore ? 0 : POLL_MS);
				} else {
					void refreshLiveState();
				}
			} catch (error) {
				if (cancelled) return;
				loadError = error instanceof Error ? error.message : String(error);
				timer = setTimeout(() => void pollDurable(), POLL_MS);
			}
		}

		async function loadRunRecord(): Promise<RunRecord | null> {
			const runs: RunRecord[] = await fetchRuns();
			return runs.find((run) => run.invocationId === id) ?? null;
		}

		void pollDurable();
		return () => {
			cancelled = true;
			if (timer !== null) clearTimeout(timer);
		};
	});

	const startedEvent = $derived(events.find((event) => event.event === 'run_started'));
	const terminalEvent = $derived(events.find((event) => event.event === 'run_completed'));
	const completedStatements = $derived(
		events.filter((event) => event.event === 'statement_completed')
	);
	const totalStatements = $derived(startedEvent?.totalStatements ?? null);

	const outcome = $derived<RunStatus>(status);

	const OUTCOME_COLOR: Record<string, string> = {
		running: 'var(--sb-secondary)',
		succeeded: 'var(--sb-success)',
		failed: 'var(--sb-error)',
		cancelled: 'var(--sb-warning)',
		unresponsive: 'var(--sb-warning)',
		presumed_failed: 'var(--sb-warning)'
	};

	async function requestCancel(): Promise<void> {
		if (
			!window.confirm(
				'Cancel this build? Direct mode may leave the selected closure partially rebuilt. Rerunning is safe.'
			)
		)
			return;
		signalling = true;
		try {
			const result = await cancelBuild(invocationId);
			forceAvailable = Boolean(result.forceAvailable);
		} catch (error) {
			loadError = error instanceof Error ? error.message : String(error);
		} finally {
			signalling = false;
		}
	}

	async function requestKill(): Promise<void> {
		signalling = true;
		try {
			await killBuild(invocationId);
			forceAvailable = false;
		} catch (error) {
			loadError = error instanceof Error ? error.message : String(error);
		} finally {
			signalling = false;
		}
	}

	// ── the pipeline growing: per-model status from replay/realize events ─────
	type ModelRunState = { state: 'running' | 'done' | 'failed'; rows: number | null };

	const modelStates = $derived.by((): Map<string, ModelRunState> => {
		const states = new Map<string, ModelRunState>();
		for (const event of events) {
			const model: string | null = modelForStep(event.stepId);
			if (model === null) continue;
			if (event.event === 'statement_started') {
				if (!states.has(model)) states.set(model, { state: 'running', rows: null });
			}
			if (event.event === 'statement_completed') {
				if (event.errorMessage) states.set(model, { state: 'failed', rows: null });
				else if ((event.stepId ?? '').startsWith('replay_')) {
					states.set(model, { state: 'done', rows: event.writtenRows ?? null });
				} else if ((event.stepId ?? '').startsWith('replace_stable_binding_')) {
					// A switchover is the whole unit of work for this model, so its
					// completion is terminal rather than a step towards a later replay.
					states.set(model, { state: 'done', rows: null });
				} else if (states.get(model)?.state !== 'done') {
					states.set(model, { state: 'running', rows: null });
				}
			}
		}
		return states;
	});

	function modelForStep(stepId: string | null): string | null {
		if (stepId === null) return null;
		if (stepId.startsWith('replay_')) {
			const name: string = stepId.slice('replay_'.length);
			return project.models.some((model) => model.name === name) ? name : null;
		}
		const byRelation = project.models.find(
			(model) =>
				stepId.endsWith(`_${model.relationName}`) || stepId.endsWith(`_mv__${model.name}`)
		);
		return byRelation?.name ?? null;
	}

	const fullGraph = $derived<Graph>(buildLogicalGraph(project));

	const mutedIds = $derived(
		new Set<string>(
			fullGraph.nodes
				.filter(
					(node) => node.logicalType !== 'source' && !modelStates.has(node.logicalName)
				)
				.map((node) => node.id)
		)
	);

	// A promotion rebinds views; nothing is rebuilt, so the vocabulary changes.
	const isPromotion = $derived(commandLine.startsWith('deployment promote'));

	const notes = $derived.by(() => {
		const map = new Map<string, { text: string; tone: 'info' | 'warn' }>();
		for (const node of fullGraph.nodes) {
			const state: ModelRunState | undefined = modelStates.get(node.logicalName);
			if (state === undefined) continue;
			if (state.state === 'failed') {
				map.set(node.id, { text: 'failed', tone: 'warn' });
			} else if (state.state === 'running') {
				// MV-cascaded models never get their own replay step — once the run
				// succeeds, their rebuild happened through the roots' replay.
				map.set(node.id, {
					text: running
						? isPromotion
							? 'switching…'
							: 'rebuilding…'
						: outcome === 'succeeded'
							? isPromotion
								? 'switched'
								: 'rebuilt'
							: 'incomplete',
					tone: running || outcome === 'succeeded' ? 'info' : 'warn'
				});
			} else {
				map.set(node.id, {
					text:
						state.rows === null
							? isPromotion
								? 'switched'
								: 'rebuilt'
							: `${formatCompact(state.rows)} rows`,
					tone: 'info'
				});
			}
		}
		return map;
	});

	// Newest first; started events are transient noise once completed.
	const timeline = $derived(
		[...events]
			.filter(
				(event) => event.event !== 'statement_started' || running
			)
			.reverse()
			.slice(0, 400)
	);

	const durationSeconds = $derived.by((): number | null => {
		if (record !== null) return record.durationMs / 1000;
		if (startedEvent === undefined) return null;
		const start: number = Date.parse(`${startedEvent.emittedAt.replace(' ', 'T')}Z`);
		const last: RunEvent | undefined = events[events.length - 1];
		const end: number =
			running || last === undefined
				? Date.now()
				: Date.parse(`${last.emittedAt.replace(' ', 'T')}Z`);
		return Math.max((end - start) / 1000, 0);
	});
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
	{:else}
	<!-- header -->
	<div class="flex shrink-0 flex-wrap items-center gap-3 border-b border-border px-[18px] py-3">
		<a href="/runs" class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 font-mono text-[11px]">
			<ArrowLeftIcon size={12} /> runs
		</a>
		<span
			class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10.5px]"
			style:border-color="color-mix(in srgb, {OUTCOME_COLOR[outcome]} 40%, var(--border))"
			style:color={OUTCOME_COLOR[outcome]}
		>
			<span
				class="h-1.5 w-1.5 rounded-full {outcome === 'running' ? 'animate-pulse' : ''}"
				style:background={OUTCOME_COLOR[outcome]}
			></span>
			{outcome}
		</span>
		<code class="code text-[12px]">{invocationId.slice(0, 8)}</code>
		<code
			class="bg-[var(--sb-inset)] min-w-0 flex-1 truncate rounded-[4px] border border-border px-2.5 py-1 font-mono text-[11px]"
			>$ stb {commandLine}</code
		>
		<span class="text-muted-foreground shrink-0 font-mono text-[11px]">
			{#if durationSeconds !== null}{formatDuration(durationSeconds)}{/if}
			{#if totalStatements !== null}
				· {completedStatements.length}/{totalStatements} statements
			{/if}
		</span>
		{#if ownedRunning && running}
			<button
				class="rounded border border-border px-2.5 py-1 font-mono text-[10.5px] text-[var(--sb-warning)]"
				disabled={signalling}
				onclick={() => void requestCancel()}>Cancel</button
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
				disabled={signalling}
				onclick={() => void requestKill()}>Force kill</button
			>
		{/if}
	</div>
	{#if status === 'unresponsive' || status === 'presumed_failed'}
		<div class="border-b border-border px-[18px] py-2 font-mono text-[11px]" style:color="var(--sb-warning)">
			{status === 'presumed_failed' ? 'Presumed failed' : 'Unresponsive'} — no signal for
			{lastSignalAgeSeconds ?? 0}s. Last activity: {record?.lastActivity ?? 'unknown'}.
			The process may recover; rerunning the build is safe once it is presumed failed.
			{#if status === 'presumed_failed'}
				<a href="/plan" class="pl-2 underline">Rerun from Plan</a>
			{/if}
		</div>
	{/if}

	{#if loadError}
		<div class="p-[18px]">
			<p class="font-mono text-[12px]" style:color="var(--sb-error)">{loadError}</p>
		</div>
	{:else}
		<!-- progress -->
		{#if totalStatements !== null && totalStatements > 0}
			<div class="shrink-0 px-[18px] pt-3">
				<div class="h-[4px] w-full overflow-hidden rounded-full bg-[var(--sb-inset)]">
					<div
						class="h-full rounded-full transition-all"
						style:width="{Math.min((completedStatements.length / totalStatements) * 100, 100)}%"
						style:background={OUTCOME_COLOR[outcome]}
					></div>
				</div>
			</div>
		{/if}

		<!-- the pipeline, growing as replays land -->
		<div class="h-[380px] shrink-0 border-b border-border">
			<LineageCanvas
				{project}
				graph={fullGraph}
				{mutedIds}
				{notes}
				groupMode="none"
				compactNodes
				embedded
			/>
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
				{#each timeline as event (event.sequence)}
					<div
						class="flex items-center gap-3 border-b border-[var(--border-subtle)] px-3 py-1.5 last:border-b-0"
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
										? OUTCOME_COLOR[outcome]
										: 'var(--sb-secondary)'}>{event.event.replace('_', ' ')}</span
								>
							{/if}
						</span>
						<span class="code min-w-0 flex-1 truncate text-[11.5px]"
							>{event.stepId ?? (event.event === 'run_completed' ? event.outcome : 'run started')}</span
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
					</div>
				{/each}
			</div>
		</div>
	{/if}
	{/if}
</div>
