<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left';
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw';
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
	import { refreshDeployments, refreshLiveState } from '$lib/api/store.svelte';
	import { buildLogicalGraph } from '$lib/domain/derive';
	import { formatCompact, formatDuration, formatTimestamp } from '$lib/domain/format';
	import type { Graph, Project } from '$lib/domain/types';
	import { consumeRunDetail } from './state';
	import type { RunDetailSnapshot } from './state';
	import { buildTimeline } from './utils';

	const project: Project = getProject();
	const invocationId = $derived(page.params.id ?? '');

	let events = $state<RunEvent[]>([]);
	let running = $state<boolean>(true);
	let status = $state<RunStatus>('running');
	let exitCode = $state<number | null>(null);
	let stderr = $state<string>('');
	let owned = $state<boolean>(false);
	let ownedRunning = $state<boolean>(false);
	let ownerInvocationId = $state<string | null>(null);
	let forceAvailable = $state<boolean>(false);
	let signalling = $state<boolean>(false);
	let lastSignalAgeSeconds = $state<number | null>(null);
	let record = $state<RunRecord | null>(null);
	let commandLine = $state<string>('build');
	let loadError = $state<string | null>(null);
	let pollError = $state<string | null>(null);
	let notFound = $state<boolean>(false);
	let initialLoading = $state<boolean>(true);

	const POLL_MS: number = 1200;

	$effect(() => {
		const id: string = invocationId;
		events = [];
		record = null;
		stderr = '';
		owned = false;
		ownedRunning = false;
		ownerInvocationId = null;
		running = true;
		status = 'running';
		exitCode = null;
		commandLine = 'build';
		loadError = null;
		pollError = null;
		initialLoading = true;
		forceAvailable = false;
		lastSignalAgeSeconds = null;
		notFound = false;
		let cancelled: boolean = false;
		let timer: ReturnType<typeof setTimeout> | null = null;
		let cursor: number = 0;

		async function pollDurable(initial?: RunDetailSnapshot): Promise<void> {
			try {
				const feed = initial?.feed ?? (await fetchRunEvents(id, cursor));
				if (cancelled) return;
				if (feed.events.length > 0) cursor = feed.events[feed.events.length - 1].sequence;
				const combinedEvents = [
					...events,
					...feed.events.filter((event) => event.event !== 'run_heartbeat')
				];
				const runStarted = combinedEvents.find((event) => event.event === 'run_started');
				events = combinedEvents;
				status = feed.status ?? 'running';
				lastSignalAgeSeconds = feed.lastSignalAgeSeconds;
				running = status === 'running' || status === 'unresponsive';
				const ownership = initial?.ownership ?? (await fetchBuildFeed(0));
				if (cancelled) return;
				owned = ownership.invocationId === id || ownership.currentInvocationId === id;
				ownedRunning = owned && ownership.running;
				ownerInvocationId = owned ? ownership.invocationId : null;
				if (owned) {
					stderr = ownership.stderr;
					forceAvailable = ownership.forceAvailable;
				}
				if (
					ownership.running &&
					page.url.searchParams.get('live') === '1' &&
					ownership.invocationId === id &&
					ownership.currentInvocationId !== null &&
					ownership.currentInvocationId !== id
				) {
					await goto(`/runs/${ownership.currentInvocationId}?live=1`, {
						replaceState: true,
						noScroll: true
					});
					return;
				}
				if (owned && !feed.found) {
					exitCode = ownership.exitCode;
					running = ownership.running;
					status = ownership.running
						? 'running'
						: ownership.exitCode === 0
							? 'succeeded'
							: 'failed';
				} else if (ownedRunning && !running) {
					running = true;
					status = 'running';
				}
				const loadedRecord =
					initial !== undefined
						? initial.record
						: ownedRunning
							? record
							: await loadRunRecord();
				if (cancelled) return;
				if (!feed.found && !owned && loadedRecord === null) {
					notFound = true;
					running = false;
					loadError = null;
					initialLoading = false;
					return;
				}
				notFound = false;
				record = loadedRecord;
				if (record !== null) {
					exitCode = record.exitCode;
					status = feed.status ?? record.status;
				}
				commandLine =
					runStarted?.displayCommand ??
					(owned && ownership.command ? ownership.command : null) ??
					record?.displayCommand ??
					record?.command ??
					'build';
				pollError = null;
				loadError = null;
				initialLoading = false;
				if (running || feed.hasMore) {
					timer = setTimeout(() => void pollDurable(), feed.hasMore ? 0 : POLL_MS);
				} else {
					void Promise.all([refreshLiveState(), refreshDeployments()]);
				}
			} catch (error) {
				if (cancelled) return;
				pollError = error instanceof Error ? error.message : String(error);
				initialLoading = false;
				timer = setTimeout(() => void pollDurable(), POLL_MS);
			}
		}

		async function loadRunRecord(): Promise<RunRecord | null> {
			const runs: RunRecord[] = await fetchRuns();
			return runs.find((run) => run.invocationId === id) ?? null;
		}

		void consumeRunDetail(id).then(
			(initial) => pollDurable(initial),
			() => pollDurable()
		);
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
	const totalStatements = $derived(
		(startedEvent?.totalStatements ?? 0) > 0 ? (startedEvent?.totalStatements ?? null) : null
	);
	const statementSummary = $derived(
		totalStatements !== null
			? `${completedStatements.length}/${totalStatements}`
			: !running && completedStatements.length > 0
				? `${completedStatements.length}`
				: null
	);
	const displayCommand = $derived(commandLine.startsWith('stb ') ? commandLine : `stb ${commandLine}`);
	const retryHref = $derived.by((): string | null => {
		if (running || !(commandLine === 'build' || commandLine.startsWith('stb build'))) return null;
		const params = new URLSearchParams();
		for (const selector of startedEvent?.selectors ?? []) params.append('select', selector);
		if (startedEvent?.startTime) params.set('start', startedEvent.startTime);
		const query = params.toString();
		return query ? `/plan?${query}` : '/plan';
	});

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
			const result = await cancelBuild(ownerInvocationId ?? invocationId);
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
			await killBuild(ownerInvocationId ?? invocationId);
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
	const executedIds = $derived(new Set<string>(startedEvent?.executedLogicalIds ?? []));
	const contextIds = $derived(new Set<string>(startedEvent?.contextLogicalIds ?? []));
	const runGraph = $derived<Graph>({
		nodes: fullGraph.nodes.filter((node) => executedIds.has(node.id) || contextIds.has(node.id)),
		edges: fullGraph.edges.filter(
			(edge) =>
				(executedIds.has(edge.source) || contextIds.has(edge.source)) &&
				(executedIds.has(edge.target) || contextIds.has(edge.target))
		)
	});
	const recordedScopeCount = $derived(executedIds.size + contextIds.size);
	const missingScopeCount = $derived(
		recordedScopeCount - runGraph.nodes.length
	);

	const mutedIds = $derived(
		new Set<string>(
			runGraph.nodes.filter((node) => contextIds.has(node.id)).map((node) => node.id)
		)
	);

	// A promotion rebinds views; nothing is rebuilt, so the vocabulary changes.
	const isPromotion = $derived(
		(startedEvent?.command ?? record?.command ?? commandLine) === 'deployment promote'
	);

	const notes = $derived.by(() => {
		const map = new Map<string, { text: string; tone: 'info' | 'warn' }>();
		for (const node of runGraph.nodes) {
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

	const timeline = $derived(buildTimeline(events, running));
	const metadataPreparationCount = $derived(numberedStepCount('prepare_metadata_'));
	const metadataMigrationCount = $derived(numberedStepCount('migrate_metadata_'));
	const candidateMetadataCount = $derived(numberedStepCount('persist_candidate_metadata_'));
	const publicationCount = $derived(numberedStepCount('persist_publish_event_'));
	const reconcileCount = $derived(numberedStepCount('persist_reconcile_state_'));

	function numberedStepCount(prefix: string): number {
		return Math.max(
			0,
			...events.map((event) => {
				const match = event.stepId?.match(new RegExp(`^${prefix}(\\d+)$`));
				return match ? Number(match[1]) : 0;
			})
		);
	}

	function eventStepLabel(event: RunEvent): string {
		const stepId = event.stepId;
		if (stepId === null) {
			if (event.event === 'run_completed') return event.outcome ?? 'completed';
			if (event.event === 'run_started' && event.startupTimings) {
				return `${displayCommand} · prepared in ${formatDuration(event.startupTimings.totalMs / 1000)} (compile ${formatDuration(event.startupTimings.compileMs / 1000)}, observability ${formatDuration(event.startupTimings.observabilityMs / 1000)}, warehouse plan ${formatDuration(event.startupTimings.planningMs / 1000)})`;
			}
			return displayCommand;
		}
		if (event.event === 'audit_started' || event.event === 'audit_completed') {
			const statusLabel = event.status ? ` · ${humanizeIdentifier(event.status)}` : '';
			const failureLabel =
				(event.failureCount ?? 0) > 0 ? ` · ${event.failureCount} failures` : '';
			return `${stepId}${statusLabel}${failureLabel}`;
		}
		const metadataStep = stepId.match(/^prepare_metadata_(\d+)$/);
		if (metadataStep) {
			return numberedLabel('Prepare metadata schema', metadataStep[1], metadataPreparationCount);
		}
		const persistenceStep = stepId.match(/^persist_candidate_metadata_(\d+)$/);
		if (persistenceStep) {
			return numberedLabel('Record deployment metadata', persistenceStep[1], candidateMetadataCount);
		}
		const migrationStep = stepId.match(/^migrate_metadata_(\d+)$/);
		if (migrationStep) {
			return numberedLabel('Prepare metadata schema', migrationStep[1], metadataMigrationCount);
		}
		const publicationStep = stepId.match(/^persist_publish_event_(\d+)$/);
		if (publicationStep) {
			return numberedLabel('Record publication', publicationStep[1], publicationCount);
		}
		const reconcileStep = stepId.match(/^persist_reconcile_state_(\d+)$/);
		if (reconcileStep) {
			return numberedLabel('Record reconciled metadata', reconcileStep[1], reconcileCount);
		}
		const auditStep = stepId.match(/^audit_\d+_(.+)_(count|sample)$/);
		if (auditStep) {
			return `${auditStep[2] === 'count' ? 'Check audit' : 'Sample audit failures'} · ${auditStep[1]}`;
		}
		const exact: Record<string, string> = {
			prepare_target_database: 'Ensure target database exists',
			assert_candidate_metadata: 'Validate deployment metadata',
			assert_candidate_unpublished: 'Confirm deployment is unpublished',
			wait_for_virtual_live_stabilization: 'Wait for source stabilization',
			wait_for_live_stabilization: 'Wait for source stabilization',
			capture_boundary_time: 'Capture replay boundary',
			read_boundary_time: 'Read replay boundary',
			replace_active_view: 'Repair active view'
		};
		if (exact[stepId]) return exact[stepId];
		const prefixes: [string, string][] = [
			['assert_candidate_relation_', 'Check candidate relation'],
			['prepare_source_', 'Prepare source'],
			['replace_stable_binding_', 'Publish'],
			['remove_stable_binding_', 'Unpublish'],
			['drop_', 'Remove existing relation'],
			['realize_', 'Create relation'],
			['attach_source_', 'Activate source'],
			['activate_source_', 'Activate source'],
			['capture_replay_', 'Capture replay range'],
			['capture_watermark_', 'Capture source watermark'],
			['assert_qualifying_input_', 'Verify replayable input'],
			['seed_', 'Seed replay input'],
			['replay_', 'Replay source data'],
			['read_readiness_', 'Measure source readiness'],
			['assert_readiness_', 'Verify source readiness']
		];
		for (const [prefix, label] of prefixes) {
			if (stepId.startsWith(prefix)) return `${label} · ${stepId.slice(prefix.length)}`;
		}
		const numbered: [string, string][] = [
			['remove_obsolete_binding_', 'Remove obsolete binding'],
			['cleanup_relation_', 'Delete retained relation'],
			['record_direct_fingerprint_', 'Record build fingerprint'],
			['record_terminal_observation_', 'Record run result']
		];
		for (const [prefix, label] of numbered) {
			if (stepId.startsWith(prefix)) return `${label} (${Number(stepId.slice(prefix.length))})`;
		}
		return stepId;
	}

	function humanizeIdentifier(value: string): string {
		const words = value.replaceAll('_', ' ');
		return words.charAt(0).toUpperCase() + words.slice(1);
	}

	function numberedLabel(label: string, rawIndex: string, total: number): string {
		const index = Number(rawIndex);
		return total > 1 ? `${label} (${index}/${total})` : label;
	}

	const durationSeconds = $derived.by((): number | null => {
		if (record !== null && record.status !== 'running' && record.status !== 'unresponsive') {
			return record.durationMs / 1000;
		}
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
			style:border-color="color-mix(in srgb, {OUTCOME_COLOR[outcome]} 40%, var(--border))"
			style:color={OUTCOME_COLOR[outcome]}
		>
			<span
				class="h-1.5 w-1.5 rounded-full {outcome === 'running' ? 'animate-pulse' : ''}"
				style:background={OUTCOME_COLOR[outcome]}
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
						style:background={OUTCOME_COLOR[outcome]}
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
						<span
							class="code min-w-0 flex-1 truncate text-[11.5px]"
							title={event.stepId ?? undefined}>{eventStepLabel(event)}</span
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
