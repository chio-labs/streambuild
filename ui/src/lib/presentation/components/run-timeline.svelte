<script lang="ts">
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import { fetchRunStatement } from '$lib/api/main/build/fetch-run-statement';
	import type { RunEvent, RunStatement } from '$lib/api/types';
	import { formatCompact } from '$lib/formatting/main/format-compact';
	import { formatTimestamp } from '$lib/formatting/main/format-timestamp';
	import ErrorPreview from '$lib/presentation/components/error-preview.svelte';
	import SqlBlock from '$lib/presentation/components/sql-block.svelte';

	interface RunTimelineProps {
		invocationId: string;
		timeline: RunEvent[];
		running: boolean;
		ownedRunning: boolean;
		outcomeColor: string;
		eventLabels: Map<number, string>;
	}

	const { invocationId, timeline, running, ownedRunning, outcomeColor, eventLabels }: RunTimelineProps =
		$props();

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
		void invocationId;
		expandedStatementSequence = null;
		runStatements = {};
		statementLoading = new Set();
		statementErrors = {};
	});
</script>

<div class="min-h-0 flex-1 p-[18px]">
	<div class="text-[var(--sb-text-faint)] pb-2 font-mono text-[10px] uppercase tracking-[0.14em]">
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
					<span class="code min-w-0 flex-1 truncate text-[11.5px]" title={event.stepId ?? undefined}
						>{eventLabels.get(event.sequence)}</span
					>
					{#if event.writtenRows !== null && event.writtenRows !== undefined}
						<span class="shrink-0 font-mono text-[10.5px]" style:color="var(--sb-secondary)"
							>{formatCompact(event.writtenRows)} rows</span
						>
					{/if}
					{#if event.elapsedMs !== undefined}
						<span
							class="text-[var(--sb-text-faint)] w-[64px] shrink-0 text-right font-mono text-[10.5px]"
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
				{#if event.errorMessage}
					<div class="border-t border-[var(--border-subtle)] bg-[var(--sb-surface-low)] px-3 py-1.5">
						<ErrorPreview
							text={event.errorMessage}
							title="Statement error"
							subtitle={event.stepId ?? undefined}
							class="w-full"
						/>
					</div>
				{/if}
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
								artifacts={[
									{ label: 'executed', code: runStatements[event.statementSequence].sql ?? null }
								]}
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
