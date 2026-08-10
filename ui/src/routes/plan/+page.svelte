<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import CopyIcon from '@lucide/svelte/icons/copy';
	import PlayIcon from '@lucide/svelte/icons/play';
	import CheckIcon from '@lucide/svelte/icons/check';
	import RotateIcon from '@lucide/svelte/icons/rotate-ccw';
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import TerminalIcon from '@lucide/svelte/icons/terminal';
	import * as Popover from '$lib/components/ui/popover';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import SelectionCombobox from '$lib/components/plan/selection-combobox.svelte';
	import PlanGraph from '$lib/components/plan/plan-graph.svelte';
	import ReplayWindowControl from '$lib/components/plan/replay-window.svelte';
	import { getProject, fetchPlan, fetchRuns, startBuild, type RunRecord } from '$lib/api';
	import { parseSelector, rootSourcesFor, selectorToken } from '$lib/domain/derive';
	import { formatAgo, formatClock, formatCompact, formatDuration, parseUtc } from '$lib/domain/format';
	import {
		OWNERSHIP_LABEL,
		type Plan,
		type PlanSqlChangeStatus,
		type Project,
		type ReplayWindow,
		type Selector,
		type Source
	} from '$lib/domain/types';
	import type { PlanPageData } from './+page';

	let { data }: { data: PlanPageData } = $props();

	const project: Project = getProject();
	const SQL_CHANGE_LABEL: Record<PlanSqlChangeStatus, string> = {
		first_baseline: 'first build',
		query_changed: 'SQL changed',
		no_query_change: 'no SQL change',
		baseline_unavailable: 'baseline unavailable'
	};
	const SQL_CHANGE_COLOUR: Record<PlanSqlChangeStatus, string> = {
		first_baseline: 'var(--primary)',
		query_changed: 'var(--sb-warning)',
		no_query_change: 'var(--sb-text-faint)',
		baseline_unavailable: 'var(--sb-warning)'
	};

	// Selection lives in the URL, so every other surface (Graph, Pipelines,
	// Catalog) is just a link constructor and a plan is shareable.
	const urlSelectors = $derived.by((): Selector[] => {
		const raw: string[] = page.url.searchParams.getAll('select');
		return raw.map(parseSelector).filter((selector): selector is Selector => selector !== null);
	});

	/**
	 * The URL is the only source of truth for the selection and the replay
	 * window. There is deliberately no local mirror.
	 *
	 * The previous version kept `selectors` in state, wrote the URL with
	 * `replaceState`, and used an $effect to sync back — guarded by the last URL
	 * it had written. That guard could not work: `replaceState` from
	 * $app/navigation is SHALLOW routing. It updates the address bar and
	 * `page.state`, but not `page.url`. So the effect always re-ran against the
	 * stale search string, missed its guard, and reset the selection to empty —
	 * the URL gained the selector while the page insisted nothing was selected,
	 * and only a reload agreed with the address bar.
	 *
	 * Deriving straight from `page.url` and navigating with `goto` removes the
	 * mirror, the guard, and the race together.
	 */
	const selectors = $derived<Selector[]>(urlSelectors);
	const replayWindow = $derived<ReplayWindow>(windowFromUrl());

	function replayStartToken(window: ReplayWindow): string | null {
		if (window.mode === 'full') return null;
		const parsed: Date = parseUtc(window.startTime);
		if (!Number.isFinite(parsed.getTime())) return null;
		return `${parsed.toISOString().slice(0, 19)}Z`;
	}

	/** One navigation per change: two `goto` calls would race on a stale URL. */
	function applySelection(nextSelectors: Selector[], nextWindow?: ReplayWindow): void {
		const url = new URL(page.url);
		url.searchParams.delete('select');
		for (const selector of nextSelectors) {
			url.searchParams.append('select', selectorToken(selector));
		}
		if (nextWindow) {
			const start: string | null = replayStartToken(nextWindow);
			if (start === null) url.searchParams.delete('start');
			else url.searchParams.set('start', start);
		}
		void goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	}

	function setSelectors(next: Selector[]): void {
		applySelection(next, next.length === 0 ? { mode: 'full' } : undefined);
	}

	// The replay window is URL-addressable too, so an entire plan — selection AND
	// cutoff — is shareable and round-trips through paste-to-preview.
	function windowFromUrl(): ReplayWindow {
		const raw: string | null = page.url.searchParams.get('start');
		if (!raw || urlSelectors.length === 0) return { mode: 'full' };
		const parsed: Date = parseUtc(raw);
		if (!Number.isFinite(parsed.getTime())) return { mode: 'full' };
		return { mode: 'from', startTime: parsed.toISOString() };
	}

	function setReplayWindow(next: ReplayWindow): void {
		applySelection(selectors, selectors.length === 0 ? { mode: 'full' } : next);
	}

	// The plan comes from the server: the same planner the CLI uses, run against
	// a live warehouse snapshot. Refetched whenever the URL-held selection or
	// replay window changes; the previous plan stays visible while the next one
	// is in flight so the page never blanks between keystrokes.
	// svelte-ignore state_referenced_locally -- deliberate: seeded from the route
	// load; later navigations are adopted inside the effect below.
	let plan = $state<Plan | null>(data.initialPlan);
	let planError = $state<string | null>(null);
	let planLoading = $state<boolean>(false);
	// svelte-ignore state_referenced_locally -- same seeding as `plan`.
	let planRequestKey = $state<string>(data.initialKey ?? '');
	let planRequestVersion: number = 0;

	function requestPlan(tokens: string[], start: string | null): void {
		const requestVersion: number = ++planRequestVersion;
		planLoading = true;
		fetchPlan(tokens, start)
			.then((next) => {
				if (requestVersion !== planRequestVersion) return;
				plan = next;
				planError = null;
			})
			.catch((error: Error) => {
				if (requestVersion !== planRequestVersion) return;
				planError = error.message;
			})
			.finally(() => {
				if (requestVersion !== planRequestVersion) return;
				planLoading = false;
			});
	}

	/** The physical column(s) the replay window bounds on, by boundary mode. */
	function boundaryColumns(root: Plan['replayRoots'][number]): string | null {
		const columns = root.replayColumns;
		if (root.boundaryMode === 'offsets') {
			const pair: string = [columns.partition, columns.offset].filter(Boolean).join(' / ');
			return pair || null;
		}
		if (root.boundaryMode === 'timestamp' || root.boundaryMode === 'cursor') {
			return columns.timestamp ?? null;
		}
		return columns.landed_at ?? null;
	}

	let executing = $state<boolean>(false);
	let executeError = $state<string | null>(null);
	let protectionConfirmations = $state<Record<string, string>>({});
	const missingProtections = $derived(
		(plan?.protections ?? []).filter(
			(protection) =>
				protectionConfirmations[protection.pipelineName] !== protection.confirmation
		)
	);
	const acceptedConfirmations = $derived(
		(plan?.protections ?? [])
			.filter(
				(protection) =>
					protectionConfirmations[protection.pipelineName] === protection.confirmation
			)
			.map((protection) => protection.confirmation)
	);
	const executionCommand = $derived(
		`${plan?.command ?? 'stb build'}${acceptedConfirmations.map((value) => ` --confirm ${value}`).join('')}`
	);

	/** POST the exact planned command and follow the run live. */
	async function execute(): Promise<void> {
		executing = true;
		executeError = null;
		try {
			const tokens: string[] = selectors.map(selectorToken);
			const start: string | null = replayStartToken(replayWindow);
			const startResult = await startBuild(tokens, start, acceptedConfirmations);
			await goto(`/runs/${startResult.invocationId}?live=1`);
		} catch (error) {
			executeError = error instanceof Error ? error.message : String(error);
		} finally {
			executing = false;
		}
	}

	/** Re-run the same selection against a fresh warehouse snapshot. */
	function replan(): void {
		const tokens: string[] = selectors.map(selectorToken);
		const start: string | null = replayStartToken(replayWindow);
		requestPlan(tokens, start);
	}

	$effect(() => {
		const tokens: string[] = selectors.map(selectorToken);
		const start: string | null = replayStartToken(replayWindow);
		const rawStart: string | null = page.url.searchParams.get('start');
		const rawStartDate: Date | null = rawStart === null ? null : parseUtc(rawStart);
		const hasUrlSelector: boolean = page.url.searchParams
			.getAll('select')
			.some((token) => parseSelector(token) !== null);
		if (
			rawStart !== null &&
			(!hasUrlSelector || rawStartDate === null || !Number.isFinite(rawStartDate.getTime()))
		) {
			applySelection(selectors, { mode: 'full' });
			return;
		}
		const key: string = `${tokens.join(',')}|${start ?? ''}`;
		if (key === planRequestKey) return;
		planRequestKey = key;
		// In-page navigations refetch through the route load; adopt its result
		// instead of firing a second identical request.
		if (data.initialKey === key && data.initialPlan !== null) {
			planRequestVersion += 1;
			plan = data.initialPlan;
			planError = null;
			planLoading = false;
			return;
		}
		requestPlan(tokens, start);
	});

	const planEntries = $derived(plan?.entries ?? []);

	/**
	 * Total rows the replay will read, available only when every root was counted.
	 * A partial sum would look exact while silently omitting an unmaterialized root.
	 */
	const rowsToReplay = $derived.by((): number | null => {
		const roots: Plan['replayRoots'] = plan?.replayRoots ?? [];
		if (roots.length === 0 || roots.some((root) => root.rowsToReplay === null)) return null;
		return roots.reduce((total, root) => total + (root.rowsToReplay ?? 0), 0);
	});

	// The last RECORDED build from _streambuild_invocations — a fact to calibrate
	// expectations against, deliberately not extrapolated into a prediction.
	let lastBuild = $state<RunRecord | null>(null);
	$effect(() => {
		fetchRuns()
			.then((runs) => {
				lastBuild =
					runs.find((run) => run.command === 'build' && run.outcome === 'succeeded') ?? null;
			})
			.catch(() => {
				lastBuild = null;
			});
	});

	/** Sources rooting the closure — bounds the replay-window control. */
	const rootSources = $derived<Source[]>(
		rootSourcesFor(
			project,
			planEntries.map((entry) => entry.modelName)
		)
	);

	const selectedCount = $derived(
		planEntries.filter((entry) => entry.reason === 'selected').length
	);
	const downstreamCount = $derived(
		planEntries.filter((entry) => entry.reason === 'downstream_of_selected').length
	);
	const relationCount = $derived(
		planEntries.reduce((sum, entry) => sum + entry.relationNames.length, 0)
	);
	const riskyOwnership = $derived(
		planEntries.flatMap((entry) =>
			entry.ownership.filter((item) => item.ownership !== 'direct' && item.ownership !== 'absent')
		)
	);

	let copied = $state<boolean>(false);

	async function copyCommand(): Promise<void> {
		try {
			await navigator.clipboard.writeText(executionCommand);
			copied = true;
			setTimeout(() => (copied = false), 1600);
		} catch {
			// Clipboard can be blocked; the command is selectable text anyway.
		}
	}

	// Paste-to-preview: the inverse of autocomplete. The point of a read-only Plan
	// page is "tell me what this will do before I run it" — including for a command
	// somebody handed you.
	let pasted = $state<string>('');
	let pasteOpen = $state<boolean>(false);
	let replacedNote = $state<string>('');

	function previewPasted(): void {
		const previousCount: number = selectors.length;
		const tokens: string[] = pasted
			.replace(/^\s*(?:\$\s*)?(?:stb|streambuild)\s+(?:build|plan)\s*/, '')
			.split(/\s+/)
			.filter(Boolean);

		const next: Selector[] = [];
		let start: string | null = null;
		for (let index = 0; index < tokens.length; index += 1) {
			if (tokens[index] === '--select' && tokens[index + 1]) {
				const parsed = parseSelector(tokens[index + 1]);
				if (parsed) next.push(parsed);
				index += 1;
			} else if (tokens[index] === '--start-time' && tokens[index + 1]) {
				start = tokens[index + 1];
				index += 1;
			}
		}
		let nextWindow: ReplayWindow = { mode: 'full' };
		if (start) {
			const parsedDate = new Date(start.endsWith('Z') ? start : `${start}Z`);
			if (!Number.isNaN(parsedDate.getTime())) {
				nextWindow = { mode: 'from', startTime: parsedDate.toISOString() };
			}
		}
		applySelection(next, nextWindow);
		// Say what happened. A silent wholesale replace is the thing that makes
		// people distrust an input.
		replacedNote =
			previousCount > 0
				? `Replaced ${previousCount} ${previousCount === 1 ? 'selector' : 'selectors'} with ${next.length} from the pasted command.`
				: `Loaded ${next.length} ${next.length === 1 ? 'selector' : 'selectors'} from the pasted command.`;
		setTimeout(() => (replacedNote = ''), 6000);
		pasted = '';
		pasteOpen = false;
	}
</script>

<AppTopbar title="Plan" />

<div class="flex min-h-0 flex-1 flex-col">
	<div class="min-h-0 flex-1 overflow-y-auto">
	<!-- ── selection ───────────────────────────────────────────────────────── -->
	<div class="border-b border-border px-[18px] py-3.5">
		<div class="flex items-center gap-2 pb-2">
			<span
				id="plan-selection-label"
				class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]"
				>What to rebuild</span
			>
			<!-- Deliberately not a second input field: pasting REPLACES the selection
			     wholesale ("what does this command do?"), which is a different act from
			     building one up. Different weight, different affordance. -->
			<Popover.Root bind:open={pasteOpen}>
				<Popover.Trigger
					class="text-muted-foreground hover:text-foreground ml-auto flex items-center gap-1.5 rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
				>
					<TerminalIcon size={11} /> Preview a command
				</Popover.Trigger>
				<Popover.Content class="w-[min(440px,calc(100vw-2rem))] p-3" align="end">
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Paste a command to see what it would do
					</div>
					<input
						bind:value={pasted}
						placeholder="stb build --select pipeline:order_events"
						class="bg-[var(--sb-inset)] w-full rounded-[4px] border border-border px-2.5 py-1.5 font-mono text-[11.5px] outline-none focus:border-[var(--primary)]"
						onkeydown={(event) => {
							if (event.key === 'Enter') previewPasted();
						}}
					/>
					{#if selectors.length}
						<p class="text-[var(--sb-text-faint)] pt-2 text-[11px] leading-snug">
							Replaces the current selection of {selectors.length}
							{selectors.length === 1 ? 'selector' : 'selectors'}.
						</p>
					{/if}
					<button
						class="bg-primary mt-2 w-full rounded-[4px] px-2.5 py-1.5 font-mono text-[11px] text-white"
						onclick={previewPasted}>Preview</button
					>
				</Popover.Content>
			</Popover.Root>
		</div>

		<SelectionCombobox
			id="plan-selection"
			labelledby="plan-selection-label"
			{project}
			{selectors}
			onchange={setSelectors}
		/>

		{#if replacedNote}
			<p class="pt-2 font-mono text-[11px]" style:color="var(--sb-secondary)">{replacedNote}</p>
		{/if}

	</div>

	<!-- ── scope, as a shape ────────────────────────────────────────────────
	     Sits directly under the selection because it answers the question the
	     selection just raised: what did I actually just point at. The tables
	     below can say which models are in scope; only this says how wide the
	     blast radius is and where it stops. -->
	{#if planError}
		<div
			class="mx-[18px] my-3 rounded-[4px] border px-3 py-2 font-mono text-[12px]"
			style:border-color="color-mix(in srgb, var(--sb-error) 45%, var(--border))"
			style:color="var(--sb-error)"
		>
			{planError}
		</div>
	{:else if plan === null}
		<div class="text-muted-foreground px-[18px] py-8 font-mono text-[12px]">
			{planLoading ? 'planning…' : 'no plan yet'}
		</div>
	{:else}
	<PlanGraph {project} {plan} />
	{/if}

	<!-- ── scope ───────────────────────────────────────────────────────────── -->
	<div class="grid grid-cols-1 gap-5 px-3 py-4 sm:px-[18px] xl:grid-cols-[minmax(0,1fr)_380px]">
		<div class="flex min-w-0 flex-col gap-5">
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
				<div class="rounded-[4px] border border-border p-3">
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						You selected
					</div>
					{#if selectors.length === 0}
						<div class="font-mono text-[13px]">no selector — all models</div>
					{:else}
						<div class="font-display text-[22px] font-semibold leading-none">
							{selectors.length}
							<span class="text-muted-foreground text-[13px] font-normal"
								>{selectors.length === 1 ? 'selector' : 'selectors'}</span
							>
						</div>
						<div class="flex flex-wrap gap-1.5 pt-2">
							{#each selectors as selector (selectorToken(selector))}
								<code class="sb-tag code">{selectorToken(selector)}</code>
							{/each}
						</div>
					{/if}
				</div>

				<div
					class="rounded-[4px] border p-3"
					style:border-color="color-mix(in srgb, var(--sb-error) 45%, var(--border))"
				>
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Will be dropped and recreated
					</div>
					<div class="font-display text-[22px] font-semibold leading-none">
						{planEntries.length}
						<span class="text-muted-foreground text-[13px] font-normal">models</span>
						<span class="text-muted-foreground text-[13px] font-normal"
							>· {relationCount} relations</span
						>
					</div>
					<div class="text-muted-foreground pt-2 font-mono text-[11px]">
						{#if selectors.length === 0}
							{planEntries.length} · all models
						{:else}
							{selectedCount} selected · {downstreamCount} downstream of selection
						{/if}
					</div>
				</div>
			</div>

			<div>
				<div
					class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
				>
					Model SQL baselines
				</div>
				<div class="overflow-hidden rounded-[4px] border border-border">
					{#each planEntries as entry (entry.modelName)}
						<div class="border-b border-[var(--border-subtle)] px-2.5 py-2 last:border-b-0">
							<div class="flex items-center gap-2.5">
								<span class="code truncate text-[11px]">{entry.modelName}</span>
								<span class="text-[var(--sb-text-faint)] font-mono text-[10px]">
									{entry.reason === 'downstream_of_selected' ? 'downstream' : entry.reason}
								</span>
								{#if entry.sqlChange}
									<span
										class="ml-auto shrink-0 font-mono text-[10px]"
										style:color={SQL_CHANGE_COLOUR[entry.sqlChange.status]}
									>
										{SQL_CHANGE_LABEL[entry.sqlChange.status]}
									</span>
								{:else}
									<span class="text-[var(--sb-text-faint)] ml-auto font-mono text-[10px]">
										not compared
									</span>
								{/if}
							</div>
							{#if entry.sqlChange?.warning}
								<div class="pt-1 font-mono text-[10px]" style:color="var(--sb-warning)">
									{entry.sqlChange.warning}
								</div>
							{/if}
							{#if entry.sqlChange?.unifiedDiff}
								<details class="pt-1">
									<summary class="text-muted-foreground cursor-pointer font-mono text-[10px]">
										view SQL diff
									</summary>
									<pre
										class="bg-[var(--sb-inset)] mt-1 max-h-56 overflow-auto rounded-[3px] p-2 font-mono text-[10px] leading-relaxed"
									>{entry.sqlChange.unifiedDiff}</pre>
								</details>
							{/if}
						</div>
					{/each}
				</div>
			</div>


			<!-- destructive notice -->
			<div
				class="flex items-start gap-2.5 rounded-[4px] border px-3 py-2.5"
				style:border-color="color-mix(in srgb, var(--sb-error) 45%, var(--border))"
				style:background="color-mix(in srgb, var(--sb-error) 7%, transparent)"
			>
				<TriangleAlertIcon size={14} class="mt-[2px] shrink-0" color="var(--sb-error)" />
				<div class="text-[12px] leading-snug">
					<span class="font-medium">Destructive, and does not roll back.</span>
					A failure after teardown leaves the graph incomplete.
				</div>
			</div>

			<!-- teardown / creation -->
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
				<div>
					<div
						class="text-[var(--sb-text-faint)] flex items-baseline gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Teardown <span class="normal-case tracking-normal">— reverse dependency order</span>
					</div>
					<div class="overflow-hidden rounded-[4px] border border-border">
						{#each plan?.teardown ?? [] as action, index (action.relationName)}
							<div
								class="flex items-center gap-2.5 border-b border-[var(--border-subtle)] px-2.5 py-1.5 last:border-b-0"
							>
								<span class="text-[var(--sb-text-faint)] w-5 shrink-0 text-right font-mono text-[10px]"
									>{index + 1}</span
								>
								<span class="code truncate text-[11px]">{action.relationName}</span>
								<span class="text-[var(--sb-text-faint)] ml-auto shrink-0 font-mono text-[10px]"
									>{action.resourceKind === 'materialized_view' ? 'MV' : action.resourceKind}</span
								>
							</div>
						{/each}
					</div>
				</div>
				<div>
					<div
						class="text-[var(--sb-text-faint)] flex items-baseline gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Creation <span class="normal-case tracking-normal">— dependency order</span>
					</div>
					<div class="overflow-hidden rounded-[4px] border border-border">
						{#each plan?.creation ?? [] as action, index (action.relationName)}
							<div
								class="flex items-center gap-2.5 border-b border-[var(--border-subtle)] px-2.5 py-1.5 last:border-b-0"
							>
								<span class="text-[var(--sb-text-faint)] w-5 shrink-0 text-right font-mono text-[10px]"
									>{index + 1}</span
								>
								<span class="code truncate text-[11px]">{action.relationName}</span>
								<span class="text-[var(--sb-text-faint)] ml-auto shrink-0 font-mono text-[10px]"
									>{action.resourceKind === 'materialized_view' ? 'MV' : action.resourceKind}</span
								>
							</div>
						{/each}
					</div>
				</div>
			</div>

		</div>

		<!-- ── right rail ──────────────────────────────────────────────────── -->
		<div class="flex flex-col gap-4">
			<ReplayWindowControl
				{project}
				sources={rootSources}
				window={replayWindow}
				selectionSpecified={selectors.length > 0}
				{rowsToReplay}
				onchange={setReplayWindow}
			/>

			<!-- replay roots: where the rebuild reads from and what bounds it -->
			{#if plan?.replayRoots.length}
				<div class="rounded-[4px] border border-border p-3">
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						Replay roots
					</div>
					{#each plan.replayRoots as root (root.modelName)}
						<div class="border-b border-[var(--border-subtle)] py-1.5 last:border-b-0">
							<div class="code text-[11px]">{root.modelName}</div>
							<div class="text-[var(--sb-text-faint)] pt-0.5 font-mono text-[10px] leading-relaxed">
								reads {root.drivingInputRelationName} · {root.boundaryMode}
								{#if boundaryColumns(root)}
									on <span class="code">{boundaryColumns(root)}</span>
								{/if}
								{#if root.rowsToReplay !== null}
									· {formatCompact(root.rowsToReplay)} rows
								{/if}
							</div>
							{#if root.hasAggregateSemantics}
								<div class="pt-0.5 font-mono text-[10px]" style:color="var(--sb-warning)">
									aggregate — a start time may not bound it
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}

			<!-- planner warnings straight from the server plan -->
			{#if plan?.warnings.length}
				<div
					class="rounded-[4px] border p-3"
					style:border-color="color-mix(in srgb, var(--sb-warning) 45%, var(--border))"
				>
					<div
						class="pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
						style:color="var(--sb-warning)"
					>
						Planner warnings
					</div>
					{#each plan.warnings as warning, index (index)}
						<div class="border-b border-[var(--border-subtle)] py-1.5 last:border-b-0">
							{#if warning.relatedModel}
								<div class="code text-[11px]">{warning.relatedModel}</div>
							{/if}
							<div class="pt-0.5 font-mono text-[10.5px] leading-relaxed">{warning.message}</div>
						</div>
					{/each}
				</div>
			{/if}

			<!-- ownership hazards get their own loud block -->
			{#if riskyOwnership.length}
				<div
					class="rounded-[4px] border p-3"
					style:border-color="color-mix(in srgb, var(--sb-error) 45%, var(--border))"
				>
					<div
						class="pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
						style:color="var(--sb-error)"
					>
						Ownership hazards
					</div>
					{#each riskyOwnership as item (item.relation)}
						<div class="border-b border-[var(--border-subtle)] py-1.5 last:border-b-0">
							<div class="code text-[11px]">{item.relation}</div>
							<div class="pt-0.5 font-mono text-[10px]" style:color="var(--sb-warning)">
								{OWNERSHIP_LABEL[item.ownership]}
							</div>
						</div>
					{/each}
				</div>
			{/if}

		</div>
	</div>

	</div>

	<!-- ── hand-off ────────────────────────────────────────────────────────── -->
	<div class="bg-[var(--sb-surface-low)] shrink-0 border-t border-border px-[18px] py-3">
		{#if (plan?.protections.length ?? 0) > 0}
			<div
				class="mb-3 space-y-2 rounded-[4px] border px-3 py-2.5"
				style:border-color="color-mix(in srgb, var(--sb-warning) 45%, var(--border))"
				style:background="color-mix(in srgb, var(--sb-warning) 7%, transparent)"
			>
				{#each plan?.protections ?? [] as protection (protection.pipelineName)}
					<div class="grid gap-1.5 sm:grid-cols-[1fr_260px] sm:items-end">
						<div>
							<div class="font-mono text-[11.5px] font-semibold" style:color="var(--sb-warning)">
								Protected pipeline: {protection.pipelineName}
							</div>
							<div class="text-muted-foreground pt-0.5 text-[11.5px]">{protection.warning}</div>
						</div>
						<label class="grid gap-1 font-mono text-[10.5px] text-muted-foreground">
							Type <code>{protection.confirmation}</code> to continue
							<input
								value={protectionConfirmations[protection.pipelineName] ?? ''}
								oninput={(event) =>
									(protectionConfirmations[protection.pipelineName] = event.currentTarget.value)}
								spellcheck="false"
								class="bg-[var(--sb-inset)] rounded-[4px] border border-border px-2.5 py-1.5 font-mono text-[11px] text-foreground outline-none focus:border-[var(--sb-warning)]"
							/>
						</label>
					</div>
				{/each}
			</div>
		{/if}
		<div class="flex flex-wrap items-center gap-3">
			<div class="text-muted-foreground shrink-0 font-mono text-[10.5px]">
				Planned against the {formatClock(plan?.plannedAt ?? '')} snapshot
				{#if lastBuild}
					· last build {formatDuration(lastBuild.durationMs / 1000)}
					({lastBuild.selectedNodeCount} nodes, {formatAgo(
						lastBuild.startedAt,
						project.capturedAt
					)})
				{/if}
			</div>
			<button
				class="text-muted-foreground hover:text-foreground flex shrink-0 items-center gap-1.5 rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px] disabled:opacity-60"
				title="The warehouse may have moved since this snapshot"
				disabled={planLoading}
				onclick={replan}
			>
				<RotateIcon size={11} /> {planLoading ? 'planning…' : 'Re-plan'}
			</button>
			<code
				class="bg-[var(--sb-inset)] order-last min-w-0 basis-full truncate rounded-[4px] border border-border px-2.5 py-1.5 font-mono text-[11.5px] lg:order-none lg:ml-auto lg:flex-1 lg:basis-auto"
				>$ {executionCommand}</code
			>
			<button
				class="flex shrink-0 items-center gap-1.5 rounded-[4px] border px-2.5 py-1.5 font-mono text-[11px] {copied
					? 'border-[var(--sb-success)]'
					: 'border-border text-muted-foreground hover:text-foreground'}"
				disabled={planLoading || planError !== null || plan === null}
				onclick={copyCommand}
			>
				{#if copied}
					<CheckIcon size={12} color="var(--sb-success)" /> copied
				{:else}
					<CopyIcon size={12} /> copy
				{/if}
			</button>
			<button
				class="bg-primary flex shrink-0 items-center gap-1.5 rounded-[4px] px-3 py-1.5 font-mono text-[11px] font-medium text-white disabled:opacity-60"
				title="Runs the exact command shown, as a subprocess"
				disabled={executing || planLoading || planError !== null || plan === null || missingProtections.length > 0}
				onclick={() => void execute()}
			>
				<PlayIcon size={12} /> {executing ? 'starting…' : 'Execute'}
			</button>
		</div>
		{#if executeError}
			<div class="pt-2 font-mono text-[11px]" style:color="var(--sb-error)">{executeError}</div>
		{/if}
	</div>
</div>
