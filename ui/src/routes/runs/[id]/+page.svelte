<script lang="ts">
	import { page } from '$app/state';
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import LineageCanvas from '$lib/components/lineage/lineage-canvas.svelte';
	import {
		getProject,
		fetchBuildFeed,
		fetchRunEvents,
		fetchRuns,
		type RunEvent,
		type RunRecord
	} from '$lib/api';
	import { refreshLiveState } from '$lib/api/store.svelte';
	import { buildLogicalGraph } from '$lib/domain/derive';
	import { formatCompact, formatDuration, formatTimestamp } from '$lib/domain/format';
	import type { Graph, Project } from '$lib/domain/types';

	const project: Project = getProject();
	const invocationId = $derived(page.params.id ?? '');

	// Live runs poll the in-memory feed with a cursor; finished runs read the
	// durable timeline once. Both produce the same event shape, so everything
	// below is source-agnostic.
	let events = $state<RunEvent[]>([]);
	let running = $state<boolean>(page.url.searchParams.get('live') === '1');
	let exitCode = $state<number | null>(null);
	let stderr = $state<string>('');
	let record = $state<RunRecord | null>(null);
	let commandLine = $state<string>('build');
	let loadError = $state<string | null>(null);

	const POLL_MS: number = 1200;

	$effect(() => {
		const id: string = invocationId;
		events = [];
		record = null;
		let cancelled: boolean = false;
		let timer: ReturnType<typeof setTimeout> | null = null;
		// A plain cursor, NOT events.length: reading state synchronously here
		// would make the effect depend on its own appends and reset forever.
		let cursor: number = 0;

		async function pollLive(): Promise<void> {
			try {
				const feed = await fetchBuildFeed(cursor);
				if (cancelled || feed.invocationId !== id) {
					await loadRecorded();
					return;
				}
				cursor += feed.events.length;
				events = [...events, ...feed.events];
				stderr = feed.stderr;
				exitCode = feed.exitCode;
				running = feed.running;
				commandLine = feed.command;
				if (feed.running) {
					timer = setTimeout(() => void pollLive(), POLL_MS);
				} else {
					// The build just changed the warehouse — refresh the app snapshot.
					void refreshLiveState();
					void loadRunRecord();
				}
			} catch (error) {
				loadError = error instanceof Error ? error.message : String(error);
			}
		}

		async function loadRecorded(): Promise<void> {
			try {
				events = await fetchRunEvents(id);
				running = false;
				await loadRunRecord();
			} catch (error) {
				loadError = error instanceof Error ? error.message : String(error);
			}
		}

		async function loadRunRecord(): Promise<void> {
			const runs: RunRecord[] = await fetchRuns();
			record = runs.find((run) => run.invocationId === id) ?? null;
			if (record !== null) {
				exitCode = record.exitCode;
				commandLine = record.command;
			}
		}

		if (page.url.searchParams.get('live') === '1') void pollLive();
		else void loadRecorded();
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

	const outcome = $derived.by((): 'running' | 'succeeded' | 'failed' => {
		if (running) return 'running';
		if (terminalEvent?.outcome === 'succeeded' || exitCode === 0) return 'succeeded';
		return 'failed';
	});

	const OUTCOME_COLOR: Record<string, string> = {
		running: 'var(--sb-secondary)',
		succeeded: 'var(--sb-success)',
		failed: 'var(--sb-error)'
	};

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
					text: running ? 'rebuilding…' : outcome === 'succeeded' ? 'rebuilt' : 'incomplete',
					tone: running || outcome === 'succeeded' ? 'info' : 'warn'
				});
			} else {
				map.set(node.id, {
					text: state.rows === null ? 'rebuilt' : `${formatCompact(state.rows)} rows`,
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
	</div>

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
</div>
