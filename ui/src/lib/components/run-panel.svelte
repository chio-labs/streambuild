<script lang="ts">
	import PlayIcon from '@lucide/svelte/icons/play';
	import XIcon from '@lucide/svelte/icons/x';
	import { goto } from '$app/navigation';
	import { getProject, startBuild } from '$lib/api';
	import { protectedPipelinesForBuild } from '$lib/domain/protection';
	import type { Project } from '$lib/domain/types';

	/**
	 * The lineage CLI box, ported from SQLBuild's run panel minus providers:
	 * a bottom sheet whose editable command line is the single source of truth.
	 * Selecting graph nodes seeds it; Run executes the exact command shown.
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
	let executeError = $state<string | null>(null);
	let commandInput = $state<HTMLInputElement>();

	const seed = $derived(
		`stb build${selection.map((name) => ` --select ${name}`).join('')} --auto-approve`
	);

	$effect(() => {
		if (open && !userEdited) cmd = seed;
	});

	$effect(() => {
		if (!open) return;
		const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		queueMicrotask(() => commandInput?.focus());
		return () => returnFocus?.focus();
	});

	type ParsedCommand = {
		selectors: string[];
		startTime: string | null;
		confirmations: string[];
		error: string | null;
	};

	const FLAGS: { flag: string; hint: string; description: string }[] = [
		{ flag: '--select', hint: '<model | pipeline:name>', description: 'Limit the rebuild scope' },
		{
			flag: '--start-time',
			hint: '<YYYY-MM-DDTHH:MM:SSZ>',
			description: 'Bound the replay window'
		},
		{ flag: '--confirm', hint: '<word>', description: 'Confirm a protected pipeline' }
	];

	function parseCommand(raw: string): ParsedCommand {
		const tokens: string[] = raw.trim().split(/\s+/);
		if (tokens[0] !== 'stb' || tokens[1] !== 'build') {
			return {
				selectors: [],
				startTime: null,
				confirmations: [],
				error: 'command must start with `stb build`'
			};
		}
		const selectors: string[] = [];
		const confirmations: string[] = [];
		let startTime: string | null = null;
		let index: number = 2;
		while (index < tokens.length) {
			const token: string = tokens[index];
			if (token === '--select' && tokens[index + 1]) {
				selectors.push(tokens[index + 1]);
				index += 2;
			} else if (token === '--start-time' && tokens[index + 1]) {
				startTime = tokens[index + 1];
				index += 2;
			} else if (token === '--confirm' && tokens[index + 1]) {
				confirmations.push(tokens[index + 1]);
				index += 2;
			} else if (token === '--auto-approve' || token === '--events') {
				index += 1;
			} else {
				return {
					selectors: [],
					startTime: null,
					confirmations: [],
					error: `unsupported token '${token}' — the UI runs --select / --start-time builds`
				};
			}
		}
		if (startTime !== null && selectors.length === 0) {
			return {
				selectors: [],
				startTime: null,
				confirmations: [],
				error: '--start-time requires --select'
			};
		}
		return { selectors, startTime, confirmations, error: null };
	}

	const parsed = $derived(parseCommand(cmd));
	const protectedPipelines = $derived(protectedPipelinesForBuild(project, parsed.selectors));
	const missingProtectedPipelines = $derived(
		protectedPipelines.filter(
			(pipeline) => !parsed.confirmations.includes(pipeline.protection?.confirmation ?? '')
		)
	);

	const matchCount = $derived.by((): number => {
		const names = new Set<string>();
		for (const selector of parsed.selectors) {
			if (selector.startsWith('pipeline:')) {
				const pipeline = project.pipelines.find(
					(item) => item.name === selector.slice('pipeline:'.length)
				);
				for (const model of pipeline?.models ?? []) names.add(model);
			} else if (project.models.some((model) => model.name === selector)) {
				names.add(selector);
			}
		}
		return names.size;
	});

	function appendFlag(flag: string): void {
		userEdited = true;
		cmd = `${cmd.trim()} ${flag} `;
	}

	async function run(): Promise<void> {
		executing = true;
		executeError = null;
		try {
			const started = await startBuild(
				parsed.selectors,
				parsed.startTime,
				parsed.confirmations
			);
			open = false;
			userEdited = false;
			await goto(`/runs/${started.invocationId}?live=1`);
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
					<p class="font-mono text-[11.5px]" style:color="var(--sb-error)">{parsed.error}</p>
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
				{#each FLAGS as item (item.flag)}
					<button
						class="hover:bg-[var(--sb-hover)] flex w-full items-baseline gap-2 rounded-[3px] px-1.5 py-1 text-left"
						onclick={() => appendFlag(item.flag)}
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
				<input
					bind:this={commandInput}
					aria-label="Build command"
					bind:value={cmd}
					oninput={() => (userEdited = true)}
					onkeydown={(event) => {
						if (
							event.key === 'Enter' &&
							parsed.error === null &&
							missingProtectedPipelines.length === 0 &&
							!executing
						)
							void run();
					}}
					spellcheck="false"
					class="bg-[var(--sb-inset)] min-w-0 basis-full rounded-[4px] border border-border px-2.5 py-2 font-mono text-[12px] outline-none focus:border-[var(--primary)] sm:flex-1 sm:basis-auto"
					placeholder="stb build --select orders --auto-approve"
				/>
				<button
					class="bg-primary flex shrink-0 items-center gap-1.5 rounded-[4px] px-3.5 py-2 font-mono text-[12px] font-medium text-white disabled:opacity-50"
					disabled={parsed.error !== null || missingProtectedPipelines.length > 0 || executing}
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
