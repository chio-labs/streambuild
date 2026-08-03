<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import CopyIcon from '@lucide/svelte/icons/copy';
	import CheckIcon from '@lucide/svelte/icons/check';
	import RotateIcon from '@lucide/svelte/icons/rotate-ccw';
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import TerminalIcon from '@lucide/svelte/icons/terminal';
	import * as Popover from '$lib/components/ui/popover';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import SelectionCombobox from '$lib/components/plan/selection-combobox.svelte';
	import PlanGraph from '$lib/components/plan/plan-graph.svelte';
	import ReplayWindowControl from '$lib/components/plan/replay-window.svelte';
	import { getProject, fetchPlan, CAN_EXECUTE_BUILD } from '$lib/api';
	import { parseSelector, rootSourcesFor, selectorToken } from '$lib/domain/derive';
	import { formatClock } from '$lib/domain/format';
	import {
		OWNERSHIP_LABEL,
		type Plan,
		type Project,
		type ReplayWindow,
		type Selector,
		type Source
	} from '$lib/domain/types';

	const project: Project = getProject();

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

	/** One navigation per change: two `goto` calls would race on a stale URL. */
	function applySelection(nextSelectors: Selector[], nextWindow?: ReplayWindow): void {
		const url = new URL(page.url);
		url.searchParams.delete('select');
		for (const selector of nextSelectors) {
			url.searchParams.append('select', selectorToken(selector));
		}
		if (nextWindow) {
			if (nextWindow.mode === 'full') url.searchParams.delete('start');
			else url.searchParams.set('start', `${nextWindow.startTime.slice(0, 19)}Z`);
		}
		void goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	}

	function setSelectors(next: Selector[]): void {
		applySelection(next);
	}

	// The replay window is URL-addressable too, so an entire plan — selection AND
	// cutoff — is shareable and round-trips through paste-to-preview.
	function windowFromUrl(): ReplayWindow {
		const raw: string | null = page.url.searchParams.get('start');
		if (!raw) return { mode: 'full' };
		const parsed = new Date(raw.endsWith('Z') ? raw : `${raw}Z`);
		if (Number.isNaN(parsed.getTime())) return { mode: 'full' };
		return { mode: 'from', startTime: parsed.toISOString() };
	}

	function setReplayWindow(next: ReplayWindow): void {
		applySelection(selectors, next);
	}

	// The plan comes from the server: the same planner the CLI uses, run against
	// a live warehouse snapshot. Refetched whenever the URL-held selection or
	// replay window changes; the previous plan stays visible while the next one
	// is in flight so the page never blanks between keystrokes.
	let plan = $state<Plan | null>(null);
	let planError = $state<string | null>(null);
	let planLoading = $state<boolean>(false);
	let planRequestKey = $state<string>('');

	$effect(() => {
		const tokens: string[] = selectors.map(selectorToken);
		const start: string | null =
			replayWindow.mode === 'from' ? `${replayWindow.startTime.slice(0, 19)}Z` : null;
		const key: string = `${tokens.join(',')}|${start ?? ''}`;
		if (key === planRequestKey) return;
		planRequestKey = key;
		planLoading = true;
		fetchPlan(tokens, start)
			.then((next) => {
				plan = next;
				planError = null;
			})
			.catch((error: Error) => {
				planError = error.message;
			})
			.finally(() => {
				planLoading = false;
			});
	});

	const planEntries = $derived(plan?.entries ?? []);

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
			await navigator.clipboard.writeText(plan?.command ?? 'stb build');
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
				<Popover.Content class="w-[440px] p-3" align="end">
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

		<SelectionCombobox {project} {selectors} onchange={setSelectors} />

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
	<div class="grid gap-5 px-[18px] py-4" style:grid-template-columns="minmax(0,1fr) 380px">
		<div class="flex min-w-0 flex-col gap-5">
			<div class="grid grid-cols-2 gap-4">
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
			<div class="grid grid-cols-2 gap-4">
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
				estimate={plan?.estimate ?? null}
				onchange={setReplayWindow}
			/>

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
		<div class="flex items-center gap-3">
			<div class="text-muted-foreground shrink-0 font-mono text-[10.5px]">
				{#if CAN_EXECUTE_BUILD}
					Ready to run
				{:else}
					Read-only · planned against the {formatClock(plan?.plannedAt ?? '')} snapshot
				{/if}
			</div>
			<button
				class="text-muted-foreground hover:text-foreground flex shrink-0 items-center gap-1.5 rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px]"
				title="The warehouse may have moved since this snapshot"
			>
				<RotateIcon size={11} /> Re-plan
			</button>
			<code
				class="bg-[var(--sb-inset)] ml-auto min-w-0 flex-1 truncate rounded-[4px] border border-border px-2.5 py-1.5 font-mono text-[11.5px]"
				>$ {plan?.command ?? 'stb build'}</code
			>
			<button
				class="flex shrink-0 items-center gap-1.5 rounded-[4px] border px-2.5 py-1.5 font-mono text-[11px] {copied
					? 'border-[var(--sb-success)]'
					: 'border-border text-muted-foreground hover:text-foreground'}"
				onclick={copyCommand}
			>
				{#if copied}
					<CheckIcon size={12} color="var(--sb-success)" /> copied
				{:else}
					<CopyIcon size={12} /> copy
				{/if}
			</button>
		</div>
	</div>
</div>
