<script lang="ts">
	import { tick } from 'svelte';
	import PlayIcon from '@lucide/svelte/icons/play';
	import XIcon from '@lucide/svelte/icons/x';
	import { startBuild } from '$lib/api/main/build/start-build';
	import { getProject } from '$lib/api/main/project/get-project';
	import { canAnyPipeline } from '$lib/auth/main/can-any-pipeline';
	import { protectedPipelinesForBuild } from '$lib/domain/main/protection/protected-pipelines-for-build';
	import type { Project } from '$lib/domain/types';
	import { openRun } from '$lib/presentation/main/_open-run';
	import { completeRunCommand } from '$lib/run-command/main/complete-run-command';
	import { parseRunCommand } from '$lib/run-command/main/parse-run-command';
	import { runCommandSuggestions } from '$lib/run-command/main/run-command-suggestions';
	import { RUN_COMMAND_FLAGS } from '$lib/run-command/constants';
	import type {
		RunCommandCompletion,
		RunCommandSuggestion
	} from '$lib/run-command/types';

	/**
	 * The lineage CLI box, ported from SQLBuild's run panel minus providers:
	 * a bottom sheet whose editable command line is the single source of truth.
	 * Selecting graph nodes seeds it; Run applies those options in the pinned dev context.
	 */
	type Props = {
		open: boolean;
		/** Model names seeding the --select flags (graph selection). */
		selection: string[];
	};
	let { open = $bindable(), selection }: Props = $props();

	const project: Project = getProject();

	let cmd = $state<string>('');
	let userEdited = $state<boolean>(false);
	let executing = $state<boolean>(false);
	const buildAllowed = $derived(
		canAnyPipeline('build.direct.run') || canAnyPipeline('deployment.create')
	);
	let executeError = $state<string | null>(null);
	let commandInput = $state<HTMLInputElement>();
	let commandInputRoot = $state<HTMLDivElement>();
	let suggestionList = $state<HTMLDivElement>();
	let suggestionsOpen = $state<boolean>(false);
	let activeSuggestionValue = $state<string | null>(null);
	let caret = $state<number>(0);
	const suggestionListId = 'run-command-suggestions';
	const commandErrorId = 'run-command-error';

	const seed = $derived(
		`stb build${selection.map((name) => ` --select ${name}`).join('')} --auto-approve`
	);

	$effect(() => {
		if (open && !userEdited) cmd = seed;
	});

	$effect(() => {
		if (!open) return;
		const returnFocus: HTMLElement | null =
			document.activeElement instanceof HTMLElement ? document.activeElement : null;
		queueMicrotask(() => {
			commandInput?.focus();
			commandInput?.setSelectionRange(cmd.length, cmd.length);
			caret = cmd.length;
		});
		return () => returnFocus?.focus();
	});

	const parsed = $derived(parseRunCommand(cmd, project.target));
	const protectedPipelines = $derived(protectedPipelinesForBuild(project, parsed.selectors));
	const missingProtectedPipelines = $derived(
		protectedPipelines.filter(
			(pipeline) => !parsed.confirmations.includes(pipeline.protection?.confirmation ?? '')
		)
	);
	const suggestions = $derived(runCommandSuggestions(cmd, caret, project, protectedPipelines));
	const visibleSuggestions = $derived(suggestionsOpen ? suggestions : []);
	const activeSuggestionIndex = $derived(
		visibleSuggestions.findIndex((suggestion) => suggestion.value === activeSuggestionValue)
	);
	const activeSuggestionId = $derived(
		activeSuggestionIndex < 0 ? undefined : `run-command-suggestion-${activeSuggestionIndex}`
	);

	const matchCount = $derived.by((): number => {
		const names = new Set<string>();
		for (const selector of parsed.selectors) {
			if (selector.startsWith('pipeline:')) {
				const pipeline: Project['pipelines'][number] | undefined = project.pipelines.find(
					(item) => item.name === selector.slice('pipeline:'.length)
				);
				for (const model of pipeline?.models ?? []) names.add(model);
			} else if (project.models.some((model) => model.name === selector)) {
				names.add(selector);
			}
		}
		return names.size;
	});

	async function appendFlag(flag: string): Promise<void> {
		userEdited = true;
		cmd = `${cmd.trim()} ${flag} `;
		await tick();
		commandInput?.focus();
		commandInput?.setSelectionRange(cmd.length, cmd.length);
		caret = cmd.length;
		suggestionsOpen = true;
		activeSuggestionValue = null;
	}

	function syncCaret(input: HTMLInputElement): void {
		caret = input.selectionStart ?? input.value.length;
		suggestionsOpen = true;
		activeSuggestionValue = null;
	}

	async function scrollActiveSuggestionIntoView(): Promise<void> {
		await tick();
		suggestionList
			?.querySelector<HTMLElement>('[data-active="true"]')
			?.scrollIntoView({ block: 'nearest' });
	}

	function moveSuggestion(direction: 1 | -1): void {
		suggestionsOpen = true;
		if (suggestions.length === 0) return;
		const currentIndex: number = suggestions.findIndex(
			(suggestion) => suggestion.value === activeSuggestionValue
		);
		const nextIndex: number =
			currentIndex < 0
				? direction === 1
					? 0
					: suggestions.length - 1
				: (currentIndex + direction + suggestions.length) % suggestions.length;
		activeSuggestionValue = suggestions[nextIndex].value;
		void scrollActiveSuggestionIntoView();
	}

	async function completeSuggestion(suggestion: RunCommandSuggestion): Promise<void> {
		const completed: RunCommandCompletion = completeRunCommand(cmd, caret, suggestion.value);
		userEdited = true;
		cmd = completed.command;
		caret = completed.cursor;
		activeSuggestionValue = null;
		await tick();
		commandInput?.focus();
		commandInput?.setSelectionRange(caret, caret);
		suggestionsOpen = runCommandSuggestions(cmd, caret, project, protectedPipelines).length > 0;
	}

	function onCommandKeydown(event: KeyboardEvent & { currentTarget: HTMLInputElement }): void {
		if (event.isComposing || event.keyCode === 229) return;
		if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && suggestions.length > 0) {
			event.preventDefault();
			moveSuggestion(event.key === 'ArrowDown' ? 1 : -1);
			return;
		}
		if ((event.key === 'Enter' || event.key === 'Tab') && activeSuggestionIndex >= 0) {
			event.preventDefault();
			void completeSuggestion(visibleSuggestions[activeSuggestionIndex]);
			return;
		}
		if (event.key === 'Escape' && suggestionsOpen) {
			event.preventDefault();
			event.stopPropagation();
			suggestionsOpen = false;
			activeSuggestionValue = null;
			return;
		}
		if (
			event.key === 'Enter' &&
			parsed.error === null &&
			missingProtectedPipelines.length === 0 &&
			!executing
		) {
			void run();
		}
	}

	function closeSuggestionsOnBlur(event: FocusEvent): void {
		if (event.relatedTarget instanceof Node && commandInputRoot?.contains(event.relatedTarget)) return;
		suggestionsOpen = false;
		activeSuggestionValue = null;
	}

	async function run(): Promise<void> {
		executing = true;
		executeError = null;
		try {
			const started: { invocationId: string } = await startBuild(
				parsed.selectors,
				parsed.startTime,
				parsed.confirmations
			);
			open = false;
			userEdited = false;
			await openRun(started.invocationId);
		} catch (error) {
			executeError = error instanceof Error ? error.message : String(error);
		} finally {
			executing = false;
		}
	}

	function close(): void {
		open = false;
		userEdited = false;
		executeError = null;
		suggestionsOpen = false;
	}
</script>

<svelte:window
	onkeydown={(event) => {
		if (open && event.key === 'Escape') close();
	}}
/>

{#if open}
	<button
		class="fixed inset-0 z-40 bg-black/40"
		aria-label="Close run panel"
		onclick={close}
	></button>
	<div
		class="bg-background fixed inset-x-0 bottom-0 z-50 max-h-[85vh] overflow-y-auto rounded-t-[10px] border-t border-border shadow-2xl lg:max-h-[70vh]"
		role="dialog"
		aria-labelledby="run-panel-title"
	>
		<div class="flex items-center gap-3 border-b border-border px-[18px] py-3">
			<span id="run-panel-title" class="font-display text-[14px] font-semibold">Run</span>
			<span class="sb-tag code">build</span>
			<span class="text-[var(--sb-text-faint)] font-mono text-[11px]"
				>target {project.target} · database {project.database}</span
			>
			<button
				class="text-muted-foreground hover:text-foreground ml-auto grid h-7 w-7 place-items-center rounded-[4px] border border-border"
				aria-label="Close"
				onclick={close}
			>
				<XIcon size={13} />
			</button>
		</div>

		<div class="grid grid-cols-1 gap-4 px-3 py-4 sm:px-[18px] lg:grid-cols-[1fr_340px]">
			<div>
				<div
					class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
				>
					Selection
				</div>
				{#if parsed.error}
					<p
						id={commandErrorId}
						role="alert"
						class="font-mono text-[11.5px]"
						style:color="var(--sb-error)"
					>
						{parsed.error}
					</p>
				{:else if parsed.selectors.length === 0}
					<p class="text-muted-foreground text-[12px]">
						No --select flags — the whole project rebuilds.
					</p>
				{:else}
					<div class="flex flex-wrap items-center gap-1.5">
						{#each parsed.selectors as selector, index (`${selector}:${index}`)}
							<span class="sb-tag code">{selector}</span>
						{/each}
						<span class="text-[var(--sb-text-faint)] font-mono text-[10.5px]"
							>{matchCount} model{matchCount === 1 ? '' : 's'} selected (downstream closure
							rebuilds too)</span
						>
					</div>
				{/if}
				{#if parsed.startTime}
					<p class="text-muted-foreground pt-2 font-mono text-[11px]">
						replay bounded from {parsed.startTime}
					</p>
				{/if}
			</div>

			<div>
				<div
					class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
				>
					Flags
				</div>
				{#each RUN_COMMAND_FLAGS as item (item.flag)}
					<button
						class="hover:bg-[var(--sb-hover)] flex w-full items-baseline gap-2 rounded-[3px] px-1.5 py-1 text-left"
						onclick={() => void appendFlag(item.flag)}
					>
						<code class="code text-primary shrink-0 text-[11px]">{item.flag}</code>
						<span class="text-[var(--sb-text-faint)] code truncate text-[10px]">{item.hint}</span>
						<span class="text-muted-foreground ml-auto shrink-0 text-[10.5px]"
							>{item.description}</span
						>
					</button>
				{/each}
			</div>
		</div>

		<div class="border-t border-border px-[18px] py-3">
			{#if protectedPipelines.length > 0}
				<div
					class="mb-3 rounded-[4px] border px-3 py-2"
					style:border-color="color-mix(in srgb, var(--sb-warning) 45%, var(--border))"
					style:background="color-mix(in srgb, var(--sb-warning) 7%, transparent)"
				>
					{#each protectedPipelines as pipeline (pipeline.name)}
						<div class="text-[11.5px]" style:color="var(--sb-warning)">
							<span class="font-mono font-semibold">Protected: {pipeline.name}</span>
							<span class="text-muted-foreground"> · {pipeline.protection?.warning}</span>
						</div>
						<div class="text-muted-foreground pt-1 font-mono text-[10.5px]">
							Add <code>--confirm {pipeline.protection?.confirmation}</code> to run this build.
						</div>
					{/each}
				</div>
			{/if}
			<div class="flex flex-wrap items-center gap-2">
				<span class="text-[var(--sb-text-faint)] shrink-0 font-mono text-[13px]">$</span>
				<div
					bind:this={commandInputRoot}
					class="relative min-w-0 basis-full sm:flex-1 sm:basis-auto"
					onfocusout={closeSuggestionsOnBlur}
				>
					<input
						bind:this={commandInput}
						aria-label="Build command"
						role="combobox"
						aria-autocomplete="list"
						aria-haspopup="listbox"
						aria-expanded={visibleSuggestions.length > 0}
						aria-controls={suggestionListId}
						aria-activedescendant={activeSuggestionId}
						aria-invalid={parsed.error !== null}
						aria-describedby={parsed.error === null ? undefined : commandErrorId}
						bind:value={cmd}
						oninput={(event) => {
							userEdited = true;
							syncCaret(event.currentTarget);
						}}
						onclick={(event) => syncCaret(event.currentTarget)}
						onselect={(event) => syncCaret(event.currentTarget)}
						onkeyup={(event) => {
							if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
								syncCaret(event.currentTarget);
							}
						}}
						onkeydown={onCommandKeydown}
						spellcheck="false"
						class="bg-[var(--sb-inset)] w-full rounded-[4px] border border-border px-2.5 py-2 font-mono text-[12px] outline-none focus:border-[var(--primary)]"
						placeholder="stb build --select orders --auto-approve"
					/>
					{#if visibleSuggestions.length > 0}
						<div
							bind:this={suggestionList}
							id={suggestionListId}
							role="listbox"
							aria-label="Build command suggestions"
							class="bg-popover absolute bottom-full left-0 right-0 z-20 mb-1 max-h-[280px] overflow-y-auto rounded-[4px] border border-border shadow-lg"
						>
							{#each ['Flags', 'Pipelines', 'Models', 'Confirmations'] as group (group)}
								{@const groupedSuggestions = visibleSuggestions.filter(
									(suggestion) => suggestion.group === group
								)}
								{#if groupedSuggestions.length > 0}
									<div role="group" aria-label={group}>
										<div
											class="text-[var(--sb-text-faint)] bg-[var(--sb-surface-low)] px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em]"
										>
											{group}
										</div>
										{#each groupedSuggestions as suggestion (suggestion.value)}
											{@const suggestionIndex = visibleSuggestions.findIndex(
												(item) => item.value === suggestion.value
											)}
											<button
												type="button"
												id={`run-command-suggestion-${suggestionIndex}`}
												role="option"
												aria-selected={activeSuggestionValue === suggestion.value}
												data-active={activeSuggestionValue === suggestion.value}
												tabindex="-1"
												class="hover:bg-[var(--sb-hover)] flex w-full items-center gap-2.5 px-2.5 py-1.5 text-left"
												style:background={activeSuggestionValue === suggestion.value
													? 'var(--sb-hover)'
													: undefined}
												onpointerenter={() => (activeSuggestionValue = suggestion.value)}
												onpointerdown={(event) => event.preventDefault()}
												onclick={() => void completeSuggestion(suggestion)}
											>
												<span class="code truncate text-[11.5px]">{suggestion.primary}</span>
												<span class="text-muted-foreground ml-auto shrink-0 font-mono text-[10px]"
													>{suggestion.secondary}</span
												>
											</button>
										{/each}
									</div>
								{/if}
							{/each}
						</div>
					{/if}
				</div>
				<button
					class="bg-primary flex shrink-0 items-center gap-1.5 rounded-[4px] px-3.5 py-2 font-mono text-[12px] font-medium text-white disabled:opacity-50"
					disabled={parsed.error !== null ||
						missingProtectedPipelines.length > 0 ||
						executing ||
						!buildAllowed}
					title={buildAllowed ? undefined : 'Requires build.direct.run or deployment.create'}
					onclick={() => void run()}
				>
					<PlayIcon size={13} /> {executing ? 'starting…' : 'Run'}
				</button>
			</div>
			{#if executeError}
				<div class="pt-2 font-mono text-[11px]" style:color="var(--sb-error)">{executeError}</div>
			{/if}
		</div>
	</div>
{/if}
