<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import CopyIcon from '@lucide/svelte/icons/copy';
	import PlayIcon from '@lucide/svelte/icons/play';
	import CheckIcon from '@lucide/svelte/icons/check';
	import RotateIcon from '@lucide/svelte/icons/rotate-ccw';
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import TerminalIcon from '@lucide/svelte/icons/terminal';
	import * as Popover from '$ui-kit/popover/main';
	import AppTopbar from '$lib/presentation/components/app-topbar.svelte';
	import SelectionCombobox from '$lib/presentation/components/plan/selection-combobox.svelte';
	import PlanGraph from '$lib/presentation/components/plan/plan-graph.svelte';
	import ReplayWindowControl from '$lib/presentation/components/plan/replay-window.svelte';
	import { startBuild } from '$lib/api/main/build/start-build';
	import { fetchPlan } from '$lib/api/main/planning/fetch-plan';
	import { getProject } from '$lib/api/main/project/get-project';
	import { fetchRuns } from '$lib/api/main/runs/fetch-runs';
	import { canAnyPipeline } from '$lib/auth/main/can-any-pipeline';
	import { createPlanView } from '$lib/plan-view/main/create-plan-view';
	import type { PlanViewTypes } from '$lib/plan-view/types';
	const project = getProject();
	const buildAllowed = $derived(canAnyPipeline('build.direct.run') || canAnyPipeline('deployment.create'));
	const planView = createPlanView();
	const location = $derived(planView.readLocation(page.url));
	const selectors = $derived(location.selectors);
	const replayWindow = $derived(location.replayWindow);
	const deploymentId = $derived(location.deploymentId);
	function applySelection(
		nextSelectors: PlanViewTypes['selector'][],
		nextWindow?: PlanViewTypes['replayWindow'],
		nextDeploymentId: string | null = null
	): void {
		const nextUrl: URL = planView.selectionUrl(page.url, nextSelectors, nextWindow, nextDeploymentId);
		if (planView.locationRequestKey(nextUrl) === planView.locationRequestKey(page.url)) return;
		planRequestVersion += 1;
		planLoading = true;
		void goto(nextUrl, {
			replaceState: true,
			noScroll: true,
			keepFocus: true
		});
	}
	function setSelectors(next: PlanViewTypes['selector'][]): void {
		applySelection(next, next.length === 0 ? { mode: 'full' } : undefined);
	}
	function setReplayWindow(next: PlanViewTypes['replayWindow']): void {
		applySelection(selectors, selectors.length === 0 ? { mode: 'full' } : next);
	}
	let plan = $state<PlanViewTypes['plan'] | null>(null);
	let planError = $state<string | null>(null);
	let planLoading = $state<boolean>(true);
	let planRequestKey = $state<string>('');
	let planRequestVersion: number = 0;
	function requestKey(tokens: string[], start: string | null, deployment: string | null): string {
		return `${tokens.join(',')}|${start ?? ''}|${deployment ?? ''}`;
	}
	function requestPlan(tokens: string[], start: string | null, deployment: string | null): void {
		const requestVersion: number = ++planRequestVersion;
		planLoading = true;
		fetchPlan(tokens, start, deployment)
			.then((next) => {
				if (requestVersion !== planRequestVersion) return;
				plan = next;
				planError = null;
				if (deployment === null && next.deploymentId !== null) {
					planRequestKey = requestKey(tokens, start, next.deploymentId);
					void goto(planView.deploymentUrl(page.url, next.deploymentId), {
						replaceState: true,
						noScroll: true,
						keepFocus: true
					});
				}
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
	let executing = $state<boolean>(false);
	let executeError = $state<string | null>(null);
	let protectionConfirmations = $state<Record<string, string>>({});
	const missingProtections = $derived(
		(plan?.protections ?? []).filter(
			(protection) => protectionConfirmations[protection.pipelineName] !== protection.confirmation
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
		plan === null
			? 'preparing plan…'
			: `${plan.command}${acceptedConfirmations.map((value) => ` --confirm ${value}`).join('')}`
	);
	/** POST the planned options in the dev server's pinned context and follow the run live. */ async function execute(): Promise<void> {
		executing = true;
		executeError = null;
		try {
			const tokens: string[] = selectors.map(planView.selectorToken);
			const start: string | null = planView.replayStartToken(replayWindow);
			const startResult: Awaited<ReturnType<typeof startBuild>> = await startBuild(
				tokens,
				start,
				acceptedConfirmations,
				plan?.deploymentId ?? null
			);
			await goto(`/runs/${startResult.invocationId}?live=1`);
		} catch (error) {
			executeError = error instanceof Error ? error.message : String(error);
		} finally {
			executing = false;
		}
	}
	function replan(): void {
		const tokens: string[] = selectors.map(planView.selectorToken);
		const start: string | null = planView.replayStartToken(replayWindow);
		requestPlan(tokens, start, deploymentId);
	}
	$effect(() => {
		const tokens: string[] = selectors.map(planView.selectorToken);
		const start: string | null = planView.replayStartToken(replayWindow);
		if (planView.shouldClearReplayStart(page.url)) {
			applySelection(selectors, { mode: 'full' });
			return;
		}
		const key: string = requestKey(tokens, start, deploymentId);
		if (key === planRequestKey) return;
		planRequestKey = key;
		requestPlan(tokens, start, deploymentId);
	});
	const planEntries = $derived(plan?.entries ?? []);
	const plannedModelNames = $derived(
		Array.from(new Set((plan?.phases ?? []).flatMap((phase) => phase.modelNames)))
	);
	const plannedRelationNames = $derived(
		Array.from(new Set((plan?.phases ?? []).flatMap((phase) => phase.relationNames)))
	);
	const hasDirectPhase = $derived((plan?.phases ?? []).some((phase) => phase.mode === 'direct'));
	const rowsToReplay = $derived.by((): number | null => {
		const roots: PlanViewTypes['plan']['replayRoots'] = plan?.replayRoots ?? [];
		if (roots.length === 0 || roots.some((root) => root.rowsToReplay === null)) return null;
		return roots.reduce((total, root) => total + (root.rowsToReplay ?? 0), 0);
	});
	let lastBuild = $state<PlanViewTypes['runRecord'] | null>(null);
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
	const rootSources = $derived<PlanViewTypes['source'][]>(
		planView.rootSources(project, plannedModelNames)
	);
	const selectedCount = $derived(
		planEntries.filter((entry) => entry.reason === 'selected').length
	);
	const downstreamCount = $derived(
		planEntries.filter((entry) => entry.reason === 'downstream_of_selected').length
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
		} catch {}
	}
	let pasted = $state<string>('');
	let pasteOpen = $state<boolean>(false);
	let replacedNote = $state<string>('');
	function previewPasted(): void {
		const previousCount: number = selectors.length;
		const parsed: ReturnType<typeof planView.parseCommand> = planView.parseCommand(pasted);
		applySelection(parsed.selectors, parsed.replayWindow, parsed.deploymentId);
		replacedNote =
			previousCount > 0
				? `Replaced ${previousCount} ${previousCount === 1 ? 'selector' : 'selectors'} with ${parsed.selectors.length} from the pasted command.`
				: `Loaded ${parsed.selectors.length} ${parsed.selectors.length === 1 ? 'selector' : 'selectors'} from the pasted command.`;
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
		<div
			role="status"
			data-testid="plan-loading-state"
			class="text-muted-foreground mx-[18px] my-4 flex items-center gap-2.5 rounded-[4px] border border-border bg-[var(--sb-surface-low)] px-3 py-4 font-mono text-[12px]"
		>
			<RotateIcon size={13} class="animate-spin" />
			<div>
				<div class="text-foreground">
					{selectors.length === 0 ? 'Planning all models…' : 'Planning selected scope…'}
				</div>
				<div class="text-[var(--sb-text-faint)] pt-0.5 text-[10.5px]">
					Reading the current warehouse state
				</div>
			</div>
		</div>
	{:else}
	<PlanGraph {project} {plan} />
	{/if}

	{#if plan !== null}
		<div class="border-b border-border bg-[var(--sb-surface-low)] px-[18px] py-3">
			<div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
				<span class="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--sb-text-faint)]">
					Build mode
				</span>
				<strong class="font-mono text-[12px] uppercase" data-testid="plan-build-mode">{plan.mode}</strong>
				<span class="text-muted-foreground text-[11.5px]">
					{#if plan.mode === 'virtual'}
						changes are staged for later promotion
					{:else if plan.mode === 'mixed'}
						virtual changes are staged before direct changes are applied
					{:else}
						changes are applied immediately
					{/if}
				</span>
			</div>
			<div class="text-muted-foreground pt-1 font-mono text-[10.5px] leading-relaxed">
				Replay reads through an upper boundary captured when Execute starts, then continues with live ingestion.
				{#if plan.deploymentId !== null}
					Deployment <code class="text-foreground">{plan.deploymentId}</code> is fixed in this Plan URL.
				{/if}
			</div>
		</div>
	{/if}

	<!-- ── scope ───────────────────────────────────────────────────────────── -->
	{#if plan !== null}
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
						{#each selectors as selector (planView.selectorToken(selector))}
							<code class="sb-tag code">{planView.selectorToken(selector)}</code>
							{/each}
						</div>
					{/if}
				</div>

				<div
					class="rounded-[4px] border p-3"
					style:border-color={hasDirectPhase
						? 'color-mix(in srgb, var(--sb-error) 45%, var(--border))'
						: 'color-mix(in srgb, var(--primary) 45%, var(--border))'}
				>
					<div
						class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
					>
						{plan.mode === 'direct'
							? 'Will be dropped and recreated'
							: plan.mode === 'virtual'
								? 'Will be staged'
								: 'Runs in two phases'}
					</div>
					<div class="font-display text-[22px] font-semibold leading-none">
						{plannedModelNames.length}
						<span class="text-muted-foreground text-[13px] font-normal">models</span>
						<span class="text-muted-foreground text-[13px] font-normal"
							>· {plannedRelationNames.length} relations</span
						>
					</div>
					<div class="text-muted-foreground pt-2 font-mono text-[11px]">
						{#if plan.mode !== 'direct'}
							{plan.executionOrder.join(' → ')}
						{:else if selectors.length === 0}
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
					Execution phases
				</div>
				<div class="grid grid-cols-1 gap-3 {plan.phases.length > 1 ? 'lg:grid-cols-2' : ''}">
					{#each plan.phases as phase, phaseIndex (`${phase.mode}-${phaseIndex}`)}
						<div class="rounded-[4px] border border-border p-3">
							<div class="flex items-baseline gap-2">
								<span class="font-mono text-[10px] text-[var(--sb-text-faint)]">{phaseIndex + 1}</span>
								<strong class="font-mono text-[11.5px] uppercase">{phase.mode}</strong>
								<span class="text-muted-foreground ml-auto font-mono text-[10px]">
									{phase.effect === 'staged' ? 'staged' : 'applied immediately'}
								</span>
							</div>
							<div class="text-muted-foreground pt-1 font-mono text-[10.5px]">
								{phase.modelNames.length} models · {phase.contextModelNames.length} context · {phase.relationNames.length} relations · {phase.actions.length} actions
							</div>
							{#if phase.deploymentId !== null}
								<div class="truncate pt-1 font-mono text-[10px] text-[var(--sb-text-faint)]">
									{phase.deploymentId}
								</div>
							{/if}
							{#if phase.actions.length > 0}
								<details class="pt-2">
									<summary class="text-muted-foreground cursor-pointer font-mono text-[10px]">
										view ordered actions
									</summary>
									<div class="mt-1 max-h-48 overflow-auto rounded-[3px] bg-[var(--sb-inset)] px-2 py-1">
										{#each phase.actions as action, actionIndex (`${action.action}-${action.logicalName}-${actionIndex}`)}
											<div class="border-b border-[var(--border-subtle)] py-1 font-mono text-[10px] last:border-b-0">
												<span class="text-[var(--sb-text-faint)]">{action.phase}</span>
												· {action.action} · {action.logicalName}
												{#if action.physicalName} → {action.physicalName}{/if}
											</div>
										{/each}
									</div>
								</details>
							{/if}
						</div>
					{/each}
				</div>
			</div>

			{#if planEntries.length > 0}
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
									style:color={planView.sqlChangeColour[entry.sqlChange.status]}
									>
									{planView.sqlChangeLabel[entry.sqlChange.status]}
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
			{/if}


			<!-- destructive notice -->
			{#if hasDirectPhase}
			<div
				class="flex items-start gap-2.5 rounded-[4px] border px-3 py-2.5"
				style:border-color="color-mix(in srgb, var(--sb-error) 45%, var(--border))"
				style:background="color-mix(in srgb, var(--sb-error) 7%, transparent)"
			>
				<TriangleAlertIcon size={14} class="mt-[2px] shrink-0" color="var(--sb-error)" />
				<div class="text-[12px] leading-snug">
					<span class="font-medium">The direct phase is destructive and does not roll back.</span>
					A failure after teardown leaves the graph incomplete.
				</div>
			</div>
			{/if}

			<!-- teardown / creation -->
			{#if hasDirectPhase}
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
			{/if}

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
								{#if planView.boundaryColumns(root)}
									on <span class="code">{planView.boundaryColumns(root)}</span>
								{/if}
								{#if root.rowsToReplay !== null}
									· {planView.formatCompact(root.rowsToReplay)} rows
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
								{planView.ownershipLabel[item.ownership]}
							</div>
						</div>
					{/each}
				</div>
			{/if}

		</div>
	</div>
	{/if}

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
				{#if plan === null}
					Waiting for the current warehouse plan
				{:else}
					Planned against the {planView.formatClock(plan.plannedAt)} snapshot
					{#if lastBuild}
						· last build {planView.formatDuration(lastBuild.durationMs / 1000)}
						({lastBuild.selectedNodeCount} nodes, {planView.formatAgo(
							lastBuild.startedAt,
							project.capturedAt
						)})
					{/if}
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
				title={buildAllowed
					? "Runs these options in the dev server's pinned context"
					: 'Requires build.direct.run or deployment.create'}
				disabled={executing ||
					planLoading ||
					planError !== null ||
					plan === null ||
					missingProtections.length > 0 ||
					!buildAllowed}
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
