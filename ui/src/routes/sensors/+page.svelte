<script lang="ts">
	import AppTopbar from '$lib/presentation/components/app-topbar.svelte';
	import { can } from '$lib/auth/main/can';
	import { formatTimestamp } from '$lib/formatting/main/format-timestamp';
	import { createSensorsState } from './_state/sensors.state.svelte';
	import type { SensorSummary, SensorTick } from './types';

	const sensors = createSensorsState();

	$effect(() => sensors.start());

	const manageAllowed = $derived(can('automation.manage'));
	const manageHint = 'Requires the target-scoped automation.manage permission';
	let skipReason = $state<string>('');

	const TICK_TONES: Record<string, string> = {
		succeeded: 'var(--sb-success)',
		skipped: 'var(--sb-warning)',
		failed: 'var(--sb-error)',
		dead_lettered: 'var(--sb-error)',
		started: 'var(--sb-warning)'
	};

	function tickTone(status: string): string {
		return TICK_TONES[status] ?? 'inherit';
	}

	function sourceLabel(sensor: SensorSummary): string {
		if (sensor.kind === 'polling') {
			return `poll every ${sensor.minimumIntervalSeconds ?? 0}s`;
		}
		return sensor.eventType ?? 'event';
	}

	function tickDetail(tick: SensorTick): string {
		if (tick.errorMessage) return tick.errorMessage;
		if (tick.skipReason) return `skipped: ${tick.skipReason}`;
		if (tick.cursor) return `cursor: ${tick.cursor}`;
		return '';
	}

	function nextStatus(sensor: SensorSummary): string {
		return sensor.effectiveStatus === 'running' ? 'stopped' : 'running';
	}

	function toggleLabel(sensor: SensorSummary): string {
		return sensor.effectiveStatus === 'running' ? 'Stop' : 'Start';
	}
</script>

{#snippet caption(text: string)}
	<div class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]">
		{text}
	</div>
{/snippet}

<AppTopbar title="Sensors" />

<div class="min-h-0 flex-1 overflow-y-auto px-[18px] py-4">
	<div class="max-w-[1120px] space-y-4">
		{#if sensors.error !== null}
			<div class="rounded-[4px] border border-[var(--sb-error)] px-3 py-2 font-mono text-[11px]" style:color="var(--sb-error)">
				{sensors.error}
			</div>
		{/if}
		{#if sensors.payload !== null}
			<div class="rounded-[4px] border border-border">
				<div class="flex items-center gap-2 border-b border-border px-3 py-2" data-testid="sensor-health">
					{@render caption('Sensors')}
					<span class="text-[var(--sb-text-faint)] font-mono text-[10px]"
						>{sensors.payload.sensors.length}</span
					>
					<span class="ml-auto flex items-center gap-1.5 font-mono text-[10.5px]">
						<span
							class="h-[7px] w-[7px] rounded-full"
							style:background={sensors.payload.health.latestError
								? 'var(--sb-error)'
								: 'var(--sb-success)'}
						></span>
						dispatcher {sensors.payload.health.state}
					</span>
					{#if sensors.payload.health.latestError}
						<span
							class="max-w-[320px] truncate font-mono text-[10.5px]"
							style:color="var(--sb-error)"
							title={sensors.payload.health.latestError}
						>
							{sensors.payload.health.latestError}
						</span>
					{/if}
				</div>
				{#if sensors.actionError !== null}
					<div
						class="border-b border-[var(--border-subtle)] px-3 py-1.5 font-mono text-[11px]"
						style:color="var(--sb-error)"
						data-testid="sensor-action-error"
					>
						{sensors.actionError}
					</div>
				{/if}
				{#if sensors.payload.sensors.length === 0}
					<div class="text-[var(--sb-text-faint)] px-3 py-3 font-mono text-[11px]">
						No sensors are defined; author them under sensors/ in the project.
					</div>
				{:else}
					<table class="sb-list w-full text-left">
						<thead>
							<tr class="text-[var(--sb-text-faint)] font-mono text-[10px] uppercase tracking-[0.14em]">
								<th class="px-3 py-1.5 font-normal">Sensor</th>
								<th class="px-3 py-1.5 font-normal">Reacts to</th>
								<th class="px-3 py-1.5 font-normal">Status</th>
								<th class="px-3 py-1.5 font-normal">Last tick</th>
								<th class="px-3 py-1.5 font-normal">Retry</th>
								<th class="px-3 py-1.5 font-normal"></th>
							</tr>
						</thead>
						<tbody>
							{#each sensors.payload.sensors as sensor (sensor.name)}
								<tr
									class="border-t border-[var(--border-subtle)] align-top"
									data-testid={`sensor-row-${sensor.name}`}
									style:background={sensors.selectedSensor === sensor.name
										? 'var(--sb-hover)'
										: undefined}
								>
									<td class="px-3 py-2">
										<button
											class="hover:text-foreground font-mono text-[12px]"
											onclick={() => void sensors.selectSensor(sensor.name)}
										>
											{sensor.name}
										</button>
										{#if sensor.description}
											<div class="text-[var(--sb-text-faint)] max-w-[360px] truncate text-[10.5px]">
												{sensor.description}
											</div>
										{/if}
									</td>
									<td class="text-muted-foreground px-3 py-2 font-mono text-[10.5px]"
										>{sourceLabel(sensor)}</td
									>
									<td class="px-3 py-2">
										<span class="flex items-center gap-1.5 font-mono text-[11px]">
											<span
												class="h-[7px] w-[7px] rounded-full"
												style:background={sensor.effectiveStatus === 'running'
													? 'var(--sb-success)'
													: 'var(--sb-text-faint)'}
											></span>
											{sensor.effectiveStatus}
											{#if sensor.override !== null}
												<span class="text-[var(--sb-text-faint)] text-[10px]">(override)</span>
											{/if}
										</span>
									</td>
									<td class="px-3 py-2 font-mono text-[10.5px]">
										{#if sensor.lastTick !== null}
											<span style:color={tickTone(sensor.lastTick.status)}
												>{sensor.lastTick.status}</span
											>
											<span class="text-[var(--sb-text-faint)]">
												{formatTimestamp(sensor.lastTick.startedAt)}</span
											>
										{:else}
											<span class="text-[var(--sb-text-faint)]">never</span>
										{/if}
									</td>
									<td class="text-muted-foreground px-3 py-2 font-mono text-[10.5px]">
										{sensor.retryPolicy.maxAttempts}× / {sensor.retryPolicy.backoffSeconds}s
									</td>
									<td class="px-3 py-2 text-right">
										<button
											class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px] disabled:opacity-50"
											disabled={sensors.busy || !manageAllowed}
											title={manageAllowed ? undefined : manageHint}
											onclick={() => void sensors.setStatus(sensor.name, nextStatus(sensor))}
										>
											{toggleLabel(sensor)}
										</button>
										{#if sensor.override !== null}
											<button
												class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px] disabled:opacity-50"
												disabled={sensors.busy || !manageAllowed}
												title={manageAllowed ? undefined : manageHint}
												onclick={() => void sensors.setStatus(sensor.name, 'declared_in_code')}
											>
												Reset
											</button>
										{/if}
									</td>
								</tr>
								{#if sensors.selectedSensor === sensor.name}
									<tr>
										<td colspan="6" class="px-3 pb-2.5">
											<div
												class="rounded-[4px] border border-[var(--border-subtle)] bg-[var(--sb-inset)] px-3 py-2"
												data-testid="sensor-ticks"
											>
												{@render caption('Tick history')}
												{#if sensors.ticks.length === 0}
													<div class="text-[var(--sb-text-faint)] pt-1.5 font-mono text-[11px]">
														No ticks recorded yet.
													</div>
												{:else}
													<div class="pt-1.5">
														{#each sensors.ticks as tick (tick.tickId)}
															<div class="flex gap-3 py-[3px] font-mono text-[10.5px]">
																<span class="w-24 shrink-0" style:color={tickTone(tick.status)}
																	>{tick.status}</span
																>
																<span class="text-[var(--sb-text-faint)] w-16 shrink-0"
																	>attempt {tick.attempt}</span
																>
																<span class="text-[var(--sb-text-faint)] w-36 shrink-0"
																	>{formatTimestamp(tick.startedAt)}</span
																>
																<span
																	class="text-muted-foreground min-w-0 flex-1 truncate"
																	title={tickDetail(tick)}>{tickDetail(tick)}</span
																>
															</div>
														{/each}
													</div>
												{/if}
											</div>
										</td>
									</tr>
								{/if}
							{/each}
						</tbody>
					</table>
				{/if}
			</div>

			<div class="rounded-[4px] border border-border">
				<div class="flex items-center gap-2 border-b border-border px-3 py-2">
					{@render caption('Dead letters')}
					<span class="text-[var(--sb-text-faint)] font-mono text-[10px]"
						>{sensors.payload.deadLetterCount}</span
					>
					{#if sensors.deadLetters.length > 0}
						<input
							class="ml-auto h-6 w-56 rounded-[4px] border border-border bg-background px-2 font-mono text-[10.5px] outline-none focus:border-[var(--primary)]"
							placeholder="skip reason"
							bind:value={skipReason}
							aria-label="Skip reason"
						/>
					{/if}
				</div>
				{#if sensors.deadLetters.length === 0}
					<div
						class="text-[var(--sb-text-faint)] px-3 py-3 font-mono text-[11px]"
						data-testid="dead-letters-empty"
					>
						No unresolved dead letters.
					</div>
				{:else}
					{#each sensors.deadLetters as letter (letter.tickId)}
						<div
							class="flex items-center gap-3 border-t border-[var(--border-subtle)] px-3 py-1.5 font-mono text-[10.5px] first:border-t-0"
							data-testid={`dead-letter-${letter.eventId}`}
						>
							<span class="w-40 shrink-0 truncate text-[11px]">{letter.sensorName}</span>
							<span
								class="text-[var(--sb-text-faint)] w-44 shrink-0 truncate"
								title={letter.eventId}>{letter.eventId}</span
							>
							<span
								class="min-w-0 flex-1 truncate"
								style:color="var(--sb-error)"
								title={letter.errorMessage ?? undefined}
							>
								{letter.errorMessage ?? ''}
							</span>
							<button
								class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2 py-[3px] disabled:opacity-50"
								disabled={sensors.busy || !manageAllowed}
								title={manageAllowed ? undefined : manageHint}
								onclick={() => void sensors.retryDeadLetter(letter.sensorName, letter.eventId ?? '')}
							>
								Retry
							</button>
							<button
								class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] rounded-[4px] border border-border px-2 py-[3px] disabled:opacity-50"
								disabled={sensors.busy || !manageAllowed || skipReason.trim() === ''}
								title={manageAllowed ? 'Requires a skip reason' : manageHint}
								onclick={() =>
									void sensors.skipDeadLetter(letter.sensorName, letter.eventId ?? '', skipReason)}
							>
								Skip
							</button>
						</div>
					{/each}
				{/if}
			</div>
		{:else if sensors.loading}
			<div class="text-[var(--sb-text-faint)] font-mono text-[11px]">loading…</div>
		{/if}
	</div>
</div>
