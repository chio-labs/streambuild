<script lang="ts">
	import {
		parseAbsolute,
		toCalendarDate,
		toZoned,
		type DateValue,
		type ZonedDateTime
	} from '@internationalized/date';
	import CalendarDaysIcon from '@lucide/svelte/icons/calendar-days';
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left';
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right';
	import { DatePicker } from 'bits-ui';
	import { clamp } from '$lib/formatting/main/clamp';
	import { formatTimestamp } from '$lib/formatting/main/format-timestamp';
	import { parseUtc } from '$lib/formatting/main/parse-utc';
	import { formatUtcOffset } from '$lib/plan-view/main/format-utc-offset';
	import { replayWallTimeOccurrences } from '$lib/plan-view/main/replay-wall-time-occurrences';
	import { setReplayWallTime } from '$lib/plan-view/main/set-replay-wall-time';

	type Props = {
		value: string;
		minimum: string;
		maximum: string;
		timeZone: string;
		onapply: (value: string) => void;
	};
	let { value, minimum, maximum, timeZone, onapply }: Props = $props();

	let open = $state<boolean>(false);
	let stagedValue = $state<ZonedDateTime | null>(null);
	const draftValue = $derived(stagedValue ?? parseZoned(value));
	const minimumValue = $derived(parseZoned(minimum));
	const maximumValue = $derived(parseZoned(maximum));
	const minimumDate = $derived(toCalendarDate(minimumValue));
	const maximumDate = $derived(toCalendarDate(maximumValue));
	const draftAbsolute = $derived(draftValue.toAbsoluteString());
	const draftTime = $derived(
		`${String(draftValue.hour).padStart(2, '0')}:${String(draftValue.minute).padStart(2, '0')}`
	);
	const draftTimeMinimum = $derived(
		sameDay(draftValue, minimumValue)
			? `${String(minimumValue.hour).padStart(2, '0')}:${String(minimumValue.minute).padStart(2, '0')}`
			: undefined
	);
	const draftTimeMaximum = $derived(
		sameDay(draftValue, maximumValue)
			? `${String(maximumValue.hour).padStart(2, '0')}:${String(maximumValue.minute).padStart(2, '0')}`
			: undefined
	);
	const draftOccurrences = $derived(replayWallTimeOccurrences(draftValue, timeZone));

	function sameDay(left: ZonedDateTime, right: ZonedDateTime): boolean {
		return left.year === right.year && left.month === right.month && left.day === right.day;
	}

	function parseZoned(instant: string): ZonedDateTime {
		return parseAbsolute(parseUtc(instant).toISOString(), timeZone);
	}

	function clampDraft(next: DateValue): ZonedDateTime {
		const zoned: ZonedDateTime = toZoned(next, timeZone);
		const milliseconds: number = clamp(
			zoned.toDate().getTime(),
			minimumValue.toDate().getTime(),
			maximumValue.toDate().getTime()
		);
		return parseAbsolute(new Date(milliseconds).toISOString(), timeZone);
	}

	function handleOpenChange(nextOpen: boolean): void {
		stagedValue = nextOpen ? parseZoned(value) : null;
		open = nextOpen;
	}

	function handleValueChange(next: DateValue | undefined): void {
		if (next) stagedValue = clampDraft(next);
	}

	function setDraftTime(nextTime: string): void {
		if (!nextTime) return;
		const [hour, minute]: number[] = nextTime.split(':').map(Number);
		stagedValue = clampDraft(setReplayWallTime(draftValue, hour, minute, timeZone));
	}

	function selectOccurrence(absolute: string): void {
		stagedValue = clampDraft(parseAbsolute(absolute, timeZone));
	}

	function apply(): void {
		onapply(draftValue.toDate().toISOString());
		open = false;
	}

	function cancel(): void {
		stagedValue = null;
		open = false;
	}
</script>

<div>
	<div class="text-[var(--sb-text-faint)] mb-1 block font-mono text-[10px] uppercase tracking-[0.14em]">
		Exact start time
	</div>
	<DatePicker.Root
		value={draftValue}
		onValueChange={handleValueChange}
		{open}
		onOpenChange={handleOpenChange}
		minValue={minimumDate}
		maxValue={maximumDate}
		closeOnDateSelect={false}
		weekStartsOn={1}
		locale="en-GB"
		calendarLabel="Replay start date"
	>
		<DatePicker.Trigger
			class="bg-[var(--sb-inset)] flex w-full cursor-pointer items-center rounded-[4px] border border-border text-left outline-none transition-colors hover:border-[var(--border-strong)] focus-visible:border-[var(--primary)] focus-visible:ring-1 focus-visible:ring-[var(--primary)]"
			aria-label="Exact start time"
			title={`Current value ${formatTimestamp(value)} in ${timeZone}`}
		>
			<span class="min-w-0 flex-1 truncate px-2 py-1.5 font-mono text-[11px]">
				{formatTimestamp(value)}
			</span>
			<span class="flex self-stretch items-center border-l border-border px-2" aria-hidden="true">
				<CalendarDaysIcon size={14} class="text-muted-foreground" />
			</span>
		</DatePicker.Trigger>

		<DatePicker.Portal>
			<DatePicker.Content
				class="z-50 w-[min(296px,calc(100vw-2rem))] rounded-[5px] border border-border bg-popover p-3 text-popover-foreground shadow-xl"
				sideOffset={6}
				align="end"
				data-testid="replay-date-time-popover"
			>
				<DatePicker.Calendar>
					{#snippet children({ months, weekdays })}
						<DatePicker.Header class="flex items-center justify-between pb-2">
							<DatePicker.PrevButton
								class="hover:bg-[var(--sb-hover)] inline-flex size-7 items-center justify-center rounded-[3px] text-muted-foreground transition-colors hover:text-foreground"
								aria-label="Previous month"
							>
								<ChevronLeftIcon size={14} />
							</DatePicker.PrevButton>
							<DatePicker.Heading class="font-mono text-[11px] font-medium" />
							<DatePicker.NextButton
								class="hover:bg-[var(--sb-hover)] inline-flex size-7 items-center justify-center rounded-[3px] text-muted-foreground transition-colors hover:text-foreground"
								aria-label="Next month"
							>
								<ChevronRightIcon size={14} />
							</DatePicker.NextButton>
						</DatePicker.Header>

						{#each months as month}
							<DatePicker.Grid class="w-full border-collapse">
								<DatePicker.GridHead>
									<DatePicker.GridRow class="grid grid-cols-7">
										{#each weekdays as weekday}
											<DatePicker.HeadCell
												class="text-[var(--sb-text-faint)] py-1 text-center font-mono text-[9px] uppercase"
											>
												{weekday.slice(0, 2)}
											</DatePicker.HeadCell>
										{/each}
									</DatePicker.GridRow>
								</DatePicker.GridHead>
								<DatePicker.GridBody>
									{#each month.weeks as week}
										<DatePicker.GridRow class="grid grid-cols-7">
											{#each week as day}
												<DatePicker.Cell date={day} month={month.value} class="p-0 text-center">
													<DatePicker.Day
														class="inline-flex size-8 items-center justify-center rounded-[3px] font-mono text-[10.5px] transition-colors hover:bg-[var(--sb-hover)] data-[disabled]:pointer-events-none data-[disabled]:opacity-25 data-[outside-month]:text-[var(--sb-text-faint)] data-[selected]:bg-[var(--primary)] data-[selected]:text-[var(--primary-foreground)] data-[today]:ring-1 data-[today]:ring-inset data-[today]:ring-[var(--primary)]"
													/>
												</DatePicker.Cell>
											{/each}
										</DatePicker.GridRow>
									{/each}
								</DatePicker.GridBody>
							</DatePicker.Grid>
						{/each}
					{/snippet}
				</DatePicker.Calendar>

				<div class="mt-3 border-t border-[var(--border-subtle)] pt-3">
					<label class="block">
						<span class="text-[var(--sb-text-faint)] mb-1 block font-mono text-[9.5px] uppercase tracking-[0.14em]">
							Time
						</span>
						<input
							type="time"
							value={draftTime}
							min={draftTimeMinimum}
							max={draftTimeMaximum}
							aria-label="Replay start time of day"
							class="bg-[var(--sb-inset)] w-full rounded-[4px] border border-border px-2 py-1.5 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
							onchange={(event) => setDraftTime(event.currentTarget.value)}
						/>
					</label>
					{#if draftOccurrences.length > 1}
						<label class="block pt-2">
							<span class="text-[var(--sb-text-faint)] mb-1 block font-mono text-[9.5px] uppercase tracking-[0.14em]">
								Repeated time
							</span>
							<select
								value={draftValue.toAbsoluteString()}
								aria-label="Replay start time occurrence"
								class="bg-[var(--sb-inset)] w-full rounded-[4px] border border-border px-2 py-1.5 font-mono text-[11px] outline-none focus:border-[var(--primary)]"
								onchange={(event) => selectOccurrence(event.currentTarget.value)}
							>
								{#each draftOccurrences as occurrence, index}
									<option value={occurrence.toAbsoluteString()}>
										{index === 0 ? 'First' : 'Second'} occurrence · {formatUtcOffset(occurrence.offset)}
									</option>
								{/each}
							</select>
						</label>
					{/if}
					<div class="text-[var(--sb-text-faint)] space-y-0.5 pt-2 font-mono text-[9.5px] leading-relaxed">
						<div data-testid="replay-time-zone">{timeZone}</div>
						<div>Earliest {formatTimestamp(minimum)}</div>
						<div>Latest {formatTimestamp(maximum)}</div>
						<div class="text-muted-foreground pt-1">Selected {formatTimestamp(draftAbsolute)}</div>
					</div>
				</div>

				<div class="mt-3 flex justify-end gap-1.5 border-t border-[var(--border-subtle)] pt-3">
					<button
						type="button"
						class="rounded-[3px] border border-border px-2 py-1 font-mono text-[10.5px] text-muted-foreground hover:bg-[var(--sb-hover)] hover:text-foreground"
						onclick={cancel}
					>
						Cancel
					</button>
					<button
						type="button"
						class="rounded-[3px] border border-[var(--primary)] bg-[var(--primary)] px-2 py-1 font-mono text-[10.5px] text-[var(--primary-foreground)] hover:opacity-90"
						onclick={apply}
					>
						Apply
					</button>
				</div>
			</DatePicker.Content>
		</DatePicker.Portal>
	</DatePicker.Root>
	<div class="text-[var(--sb-text-faint)] pt-1 font-mono text-[9.5px]">{timeZone}</div>
</div>
