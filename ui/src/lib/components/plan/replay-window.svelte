<script lang="ts">
	import SpanTrack from '$lib/components/span-track.svelte';
	import {
		clamp,
		formatCompact,
		formatDaySpan,
		formatTimestamp,
		fromDateTimeLocal,
		parseUtc,
		toDateTimeLocal
	} from '$lib/domain/format';
	import type { Project, ReplayWindow, Source } from '$lib/domain/types';

	type Props = {
		project: Project;
		/** Sources that root the current rebuild closure. */
		sources: Source[];
		window: ReplayWindow;
		/** The CLI only accepts --start-time alongside at least one --select. */
		selectionSpecified: boolean;
		/**
		 * Rows the replay will read, counted server-side at plan time with the same
		 * predicate the build uses. A fact, not an estimate — which is why there is
		 * deliberately no seconds figure next to it.
		 */
		rowsToReplay: number | null;
		onchange: (next: ReplayWindow) => void;
	};
	let {
		project,
		sources,
		window: replayWindow,
		selectionSpecified,
		rowsToReplay,
		onchange
	}: Props = $props();

	// --start-time is the WORST flag to type and the BEST to render: its valid range
	// is fully bounded by data we already hold. Typed into a shell it fails at build
	// time; drawn against the retention track it fails before you commit.
	//
	// Framing is deliberately calm. Model tables are disposable derivations of the
	// source, so every direct build is ALREADY bounded by source retention — this
	// narrows the window inside an already-bounded system. It is a cost/time
	// control, not a new hazard. The durability statement lives on Sources.

	/**
	 * The earliest addressable instant across all rooting sources. Deliberately the
	 * MIN, not the max: --start-time is a global cutoff and each source replays from
	 * max(start, its own oldest), so clamping to the most-constrained source would
	 * stop you asking for history the other sources still hold.
	 */
	const retainedStartMilliseconds = $derived.by((): number | null => {
		const candidates: number[] = sources
			.map((source) => source.live.oldestEventAt)
			.filter((instant): instant is string => Boolean(instant))
			.map((instant) => parseUtc(instant).getTime())
			.filter((milliseconds) => Number.isFinite(milliseconds));
		return candidates.length === 0 ? null : Math.min(...candidates);
	});
	const boundToMilliseconds = $derived(parseUtc(project.capturedAt).getTime());
	const hasRetentionWindow = $derived(
		retainedStartMilliseconds !== null &&
			Number.isFinite(boundToMilliseconds) &&
			retainedStartMilliseconds < boundToMilliseconds
	);
	const boundFrom = $derived(
		retainedStartMilliseconds === null
			? project.capturedAt
			: new Date(retainedStartMilliseconds).toISOString()
	);
	const boundTo = $derived(project.capturedAt);
	const totalMs = $derived(
		Math.max(
			boundToMilliseconds - (retainedStartMilliseconds ?? boundToMilliseconds),
			1
		)
	);
	const canSetStartTime = $derived(selectionSpecified && hasRetentionWindow);
	const requestedStartMilliseconds = $derived(
		replayWindow.mode === 'from' ? parseUtc(replayWindow.startTime).getTime() : NaN
	);
	const effectiveStartMilliseconds = $derived.by((): number => {
		if (!Number.isFinite(requestedStartMilliseconds)) {
			return retainedStartMilliseconds ?? boundToMilliseconds;
		}
		return clamp(
			requestedStartMilliseconds,
			retainedStartMilliseconds ?? requestedStartMilliseconds,
			boundToMilliseconds
		);
	});
	const startTime = $derived(
		replayWindow.mode === 'from'
			? new Date(effectiveStartMilliseconds).toISOString()
			: boundFrom
	);

	$effect(() => {
		if (
			replayWindow.mode === 'from' &&
			canSetStartTime &&
			requestedStartMilliseconds !== effectiveStartMilliseconds
		) {
			onchange({ mode: 'from', startTime });
		}
	});

	/** Sources that cannot reach back as far as the chosen cutoff. */
	const shortSources = $derived.by((): Source[] => {
		const startMilliseconds: number = parseUtc(startTime).getTime();
		return sources.filter((source) => {
			if (!source.live.oldestEventAt) return false;
			const oldestMilliseconds: number = parseUtc(source.live.oldestEventAt).getTime();
			return Number.isFinite(oldestMilliseconds) && oldestMilliseconds > startMilliseconds;
		});
	});

	/** Slider position as a 0–1000 integer over the retention window. */
	const sliderValue = $derived(
		Math.round(
			clamp(
				(parseUtc(startTime).getTime() - parseUtc(boundFrom).getTime()) / totalMs,
				0,
				1
			) * 1000
		)
	);

	function setFromSlider(value: number): void {
		const instant = new Date(
			parseUtc(boundFrom).getTime() + (clamp(value, 0, 1000) / 1000) * totalMs
		);
		// Snap to the minute — sub-minute precision is noise for a replay boundary.
		instant.setUTCSeconds(0, 0);
		onchange({ mode: 'from', startTime: instant.toISOString() });
	}

	function setFromCalendar(value: string): void {
		if (!value) return;
		const iso: string = fromDateTimeLocal(value);
		const clamped = new Date(
			clamp(
				parseUtc(iso).getTime(),
				parseUtc(boundFrom).getTime(),
				parseUtc(boundTo).getTime()
			)
		);
		onchange({ mode: 'from', startTime: clamped.toISOString() });
	}

	function enableStartTime(): void {
		if (!canSetStartTime) return;
		onchange({
			mode: 'from',
			startTime: new Date(
				boundToMilliseconds - Math.min(totalMs, 5.5 * 86_400_000)
			).toISOString()
		});
	}

	const skippedDays = $derived(
		(parseUtc(startTime).getTime() - parseUtc(boundFrom).getTime()) / 86_400_000
	);
	const replayedDays = $derived(
		(parseUtc(boundTo).getTime() - parseUtc(startTime).getTime()) / 86_400_000
	);

	const totalRetainedRows = $derived(
		sources.reduce((sum, source) => sum + source.live.rows, 0)
	);
</script>

<div class="rounded-[4px] border border-border">
	<div class="flex items-center gap-3 border-b border-border px-3 py-2.5">
		<span
			class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]"
			>Replay window</span
		>
		<div class="ml-auto flex overflow-hidden rounded-[4px] border border-border">
			<button
				class="px-2.5 py-1 font-mono text-[10.5px] transition-colors {replayWindow.mode === 'full'
					? 'bg-[var(--sb-hover)] text-foreground'
					: 'text-muted-foreground hover:text-foreground'}"
				onclick={() => onchange({ mode: 'full' })}
			>
				Full retained
			</button>
			<button
				class="border-l border-border px-2.5 py-1 font-mono text-[10.5px] transition-colors {replayWindow.mode ===
				'from'
					? 'bg-[var(--sb-hover)] text-foreground'
					: 'text-muted-foreground hover:text-foreground'} disabled:cursor-not-allowed disabled:opacity-45"
				disabled={!canSetStartTime}
				title={!selectionSpecified
					? 'Choose at least one model or pipeline first'
					: !hasRetentionWindow
						? 'No retained source window is available yet'
						: undefined}
				onclick={enableStartTime}
			>
				From a time
			</button>
		</div>
	</div>

	<div class="flex flex-col gap-3 px-3 py-3">
		{#if sources.length === 0}
			<p class="text-muted-foreground text-[12px]">
				This selection has no rooting stream source, so there is nothing to replay.
			</p>
		{:else if !selectionSpecified}
			<p class="text-muted-foreground text-[12px]">
				Choose at least one model or pipeline to set a start time. StreamBuild requires
				<code class="code">--start-time</code> to be scoped by <code class="code">--select</code>.
			</p>
		{:else if !hasRetentionWindow}
			<p class="text-muted-foreground text-[12px]">
				A retained source window is not available yet. Build the source first, then choose a
				bounded replay start time.
			</p>
		{:else}
			<!-- retention track, with the chosen cutoff drawn on it -->
			<div>
				<div class="text-muted-foreground flex items-baseline gap-2 pb-1 font-mono text-[10px]">
					<span
						>{sources.length === 1 ? sources[0].relationName : `${sources.length} sources`} retained</span
					>
					<span class="ml-auto">{formatDaySpan(totalMs / 86_400_000)}</span>
				</div>
				<SpanTrack
					domainFrom={boundFrom}
					domainTo={boundTo}
					height={22}
					markerAt={replayWindow.mode === 'from' ? startTime : null}
					markerLabel={formatTimestamp(startTime)}
					bands={replayWindow.mode === 'full'
						? [
								{
									from: boundFrom,
									to: boundTo,
									colour: 'var(--sb-secondary)',
									opacity: 0.55,
									label: 'will replay'
								}
							]
						: [
								{
									from: boundFrom,
									to: startTime,
									colour: 'transparent',
									hatch: true,
									label: 'skipped'
								},
								{
									from: startTime,
									to: boundTo,
									colour: 'var(--sb-secondary)',
									opacity: 0.55,
									label: 'will replay'
								}
							]}
				/>
				<div
					class="text-[var(--sb-text-faint)] flex justify-between pt-1 font-mono text-[10px]"
				>
					<span>{formatTimestamp(boundFrom)}</span>
					<span>{formatTimestamp(boundTo)}</span>
				</div>
			</div>

			{#if replayWindow.mode === 'from'}
				<!-- slider + calendar, mutually bound; both clamped to the retention window -->
				<div class="flex items-center gap-3">
					<input
						type="range"
						min="0"
						max="1000"
						value={sliderValue}
						class="h-1 flex-1 cursor-pointer appearance-none rounded bg-[var(--sb-inset)] accent-[var(--primary)]"
						aria-label="Replay start time"
						onchange={(event) => setFromSlider(Number(event.currentTarget.value))}
					/>
					<input
						type="datetime-local"
						value={toDateTimeLocal(startTime)}
						min={toDateTimeLocal(boundFrom)}
						max={toDateTimeLocal(boundTo)}
						class="bg-[var(--sb-inset)] rounded-[4px] border border-border px-2 py-1 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
						onchange={(event) => setFromCalendar(event.currentTarget.value)}
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div class="rounded-[3px] border border-[var(--border-subtle)] px-2.5 py-2">
						<div class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]">
							Skipped
						</div>
						<div class="text-muted-foreground pt-1 font-mono text-[12px]">
							{formatDaySpan(Math.max(skippedDays, 0))}
						</div>
					</div>
					<div class="rounded-[3px] border border-[var(--border-subtle)] px-2.5 py-2">
						<div class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]">
							Will replay
						</div>
						<div class="pt-1 font-mono text-[12px]" style:color="var(--sb-secondary)">
							{formatDaySpan(Math.max(replayedDays, 0))}
						</div>
					</div>
				</div>
			{/if}

			<!-- estimate -->
			{#if shortSources.length && sources.length > 1}
				<p class="text-[var(--sb-text-faint)] text-[11px] leading-snug">
					{shortSources.map((source) => source.name).join(', ')} replays from
					{shortSources.length === 1
						? formatTimestamp(shortSources[0].live.oldestEventAt)
						: 'its own earliest retained event'}
				</p>
			{/if}

			{#if rowsToReplay !== null}
				<div
					class="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-t border-[var(--border-subtle)] pt-2.5 font-mono text-[11px]"
				>
					<span class="text-muted-foreground"
						>{formatCompact(rowsToReplay)} rows of {formatCompact(totalRetainedRows)} retained</span
					>
					<span class="text-[var(--sb-text-faint)] ml-auto">counted at plan time</span>
				</div>
				{#if replayWindow.mode === 'from'}
					<p class="text-[var(--sb-text-faint)] text-[11px]">
						Resulting extent {formatTimestamp(startTime)} → now
					</p>
				{/if}
			{:else}
				<p class="text-[var(--sb-text-faint)] border-t border-[var(--border-subtle)] pt-2.5 text-[11px]">
					Exact replay rows are unavailable until every rooting source can be counted.
				</p>
			{/if}
		{/if}
	</div>
</div>
