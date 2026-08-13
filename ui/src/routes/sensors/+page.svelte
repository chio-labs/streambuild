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

	const STATUS_TONES: Record<string, string> = {
		running: 'var(--sb-success)',
		stopped: 'var(--sb-muted, #8b8b8b)'
	};
	const TICK_TONES: Record<string, string> = {
		succeeded: 'var(--sb-success)',
		skipped: 'var(--sb-warning)',
		failed: 'var(--sb-error)',
		dead_lettered: 'var(--sb-error)',
		started: 'var(--sb-warning)'
	};

	function statusTone(status: string): string {
		return STATUS_TONES[status] ?? 'inherit';
	}

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

<AppTopbar title="Sensors" />

<div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
	{#if sensors.error !== null}
		<div class="pb-2 text-[12px]" style:color="var(--sb-error)">{sensors.error}</div>
	{/if}
	{#if sensors.payload !== null}
		<div class="text-muted-foreground pb-3 font-mono text-[11px]" data-testid="sensor-health">
			dispatcher {sensors.payload.health.state}
			· dead letters {sensors.payload.deadLetterCount}
			{#if sensors.payload.health.latestError}
				· <span style:color="var(--sb-error)">{sensors.payload.health.latestError}</span>
			{/if}
		</div>
		{#if sensors.actionError !== null}
			<div class="pb-2 text-[12px]" style:color="var(--sb-error)" data-testid="sensor-action-error">
				{sensors.actionError}
			</div>
		{/if}
		<table class="sb-list w-full text-left text-[12px]">
			<thead>
				<tr class="text-muted-foreground text-[11px] uppercase">
					<th class="py-1 pr-3">Sensor</th>
					<th class="py-1 pr-3">Reacts to</th>
					<th class="py-1 pr-3">Status</th>
					<th class="py-1 pr-3">Last tick</th>
					<th class="py-1 pr-3">Retry</th>
					<th class="py-1 pr-3"></th>
				</tr>
			</thead>
			<tbody>
				{#each sensors.payload.sensors as sensor (sensor.name)}
					<tr class="border-border border-t align-top" data-testid={`sensor-row-${sensor.name}`}>
						<td class="py-1.5 pr-3">
							<button
								class="hover:text-foreground font-mono"
								onclick={() => void sensors.selectSensor(sensor.name)}
							>
								{sensor.name}
							</button>
							{#if sensor.description}
								<div class="text-muted-foreground text-[11px]">{sensor.description}</div>
							{/if}
						</td>
						<td class="py-1.5 pr-3 font-mono text-[11px]">{sourceLabel(sensor)}</td>
						<td class="py-1.5 pr-3">
							<span class="font-mono" style:color={statusTone(sensor.effectiveStatus)}>
								{sensor.effectiveStatus}
							</span>
							{#if sensor.override !== null}
								<span class="text-muted-foreground text-[11px]"> (override)</span>
							{/if}
						</td>
						<td class="py-1.5 pr-3 font-mono text-[11px]">
							{#if sensor.lastTick !== null}
								<span style:color={tickTone(sensor.lastTick.status)}>{sensor.lastTick.status}</span>
								<span class="text-muted-foreground"> {formatTimestamp(sensor.lastTick.startedAt)}</span>
							{:else}
								<span class="text-muted-foreground">never</span>
							{/if}
						</td>
						<td class="py-1.5 pr-3 font-mono text-[11px]">
							{sensor.retryPolicy.maxAttempts}× / {sensor.retryPolicy.backoffSeconds}s
						</td>
						<td class="py-1.5 pr-3 text-right">
							<button
								class="border-border rounded-[3px] border px-2 py-0.5 text-[11px] disabled:opacity-50"
								disabled={sensors.busy || !manageAllowed}
								title={manageAllowed ? undefined : manageHint}
								onclick={() => void sensors.setStatus(sensor.name, nextStatus(sensor))}
							>
								{toggleLabel(sensor)}
							</button>
							{#if sensor.override !== null}
								<button
									class="border-border rounded-[3px] border px-2 py-0.5 text-[11px] disabled:opacity-50"
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
						<tr class="border-border border-t">
							<td colspan="6" class="py-2" data-testid="sensor-ticks">
								{#if sensors.ticks.length === 0}
									<div class="text-muted-foreground text-[11px]">No ticks recorded yet.</div>
								{:else}
									{#each sensors.ticks as tick (tick.tickId)}
										<div class="flex gap-3 py-0.5 font-mono text-[11px]">
											<span class="w-24" style:color={tickTone(tick.status)}>{tick.status}</span>
											<span class="text-muted-foreground w-16">attempt {tick.attempt}</span>
											<span class="text-muted-foreground w-40">{formatTimestamp(tick.startedAt)}</span>
											<span class="min-w-0 flex-1 truncate">{tickDetail(tick)}</span>
										</div>
									{/each}
								{/if}
							</td>
						</tr>
					{/if}
				{/each}
			</tbody>
		</table>
		{#if sensors.payload.sensors.length === 0}
			<div class="text-muted-foreground py-4 text-[12px]">
				No sensors are defined; author them under sensors/ in the project.
			</div>
		{/if}

		<h2 class="pt-6 pb-1 text-[12px] font-medium">Dead letters</h2>
		{#if sensors.deadLetters.length === 0}
			<div class="text-muted-foreground text-[12px]" data-testid="dead-letters-empty">
				No unresolved dead letters.
			</div>
		{:else}
			<div class="flex items-center gap-2 pb-2">
				<input
					class="border-border bg-background h-7 rounded border px-2 font-mono text-[11px]"
					placeholder="skip reason"
					bind:value={skipReason}
					aria-label="Skip reason"
				/>
			</div>
			{#each sensors.deadLetters as letter (letter.tickId)}
				<div
					class="border-border flex items-center gap-3 border-t py-1.5 font-mono text-[11px]"
					data-testid={`dead-letter-${letter.eventId}`}
				>
					<span class="w-40 truncate">{letter.sensorName}</span>
					<span class="text-muted-foreground w-40 truncate">{letter.eventId}</span>
					<span class="min-w-0 flex-1 truncate" style:color="var(--sb-error)">
						{letter.errorMessage ?? ''}
					</span>
					<button
						class="border-border rounded-[3px] border px-2 py-0.5 disabled:opacity-50"
						disabled={sensors.busy || !manageAllowed}
						title={manageAllowed ? undefined : manageHint}
						onclick={() => void sensors.retryDeadLetter(letter.sensorName, letter.eventId ?? '')}
					>
						Retry
					</button>
					<button
						class="border-border rounded-[3px] border px-2 py-0.5 disabled:opacity-50"
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
	{:else if sensors.loading}
		<div class="text-muted-foreground text-[12px]">loading…</div>
	{/if}
</div>
