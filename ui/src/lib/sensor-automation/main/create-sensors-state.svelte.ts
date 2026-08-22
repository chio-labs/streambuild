import {
	fetchDeadLetters,
	requestDeadLetterRetry,
	requestDeadLetterSkip
} from '../_api/dead-letters';
import { fetchSensors, fetchSensorTicks } from '../_api/sensor-collection';
import { requestSensorStatus } from '../_api/sensor-status';
import { createSensorsPollingResource } from '../_resources/sensors-polling.resource';
import type {
	DeadLetterActionResult,
	DeadLettersPayload,
	PendingDeadLetterAction,
	SensorsPayload,
	SensorsPollingResource,
	SensorsState,
	SensorTick,
	SensorTicksPayload
} from '../types';

export function createSensorsState(): SensorsState {
	let payload = $state<SensorsPayload | null>(null);
	let deadLetters = $state<SensorTick[]>([]);
	let selectedSensor = $state<string | null>(null);
	let ticks = $state<SensorTick[]>([]);
	let loading = $state<boolean>(true);
	let error = $state<string | null>(null);
	let actionError = $state<string | null>(null);
	let actionMessage = $state<string | null>(null);
	let busy = $state<boolean>(false);
	let pendingDeadLetterAction = $state<PendingDeadLetterAction | null>(null);
	let refreshing: boolean = false;

	async function refresh(): Promise<void> {
		if (refreshing) return;
		refreshing = true;
		try {
			const nextPayload: SensorsPayload = await fetchSensors();
			payload = nextPayload;
			error = null;
			loading = false;
			if (nextPayload.deadLetterCount === 0) {
				deadLetters = [];
			} else {
				const nextDeadLetters: DeadLettersPayload = await fetchDeadLetters();
				deadLetters = nextDeadLetters.deadLetters;
			}
			await refreshTicks();
		} catch (caught) {
			error = String(caught);
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function refreshTicks(): Promise<void> {
		if (selectedSensor === null) {
			ticks = [];
			return;
		}
		const history: SensorTicksPayload = await fetchSensorTicks(selectedSensor);
		ticks = history.ticks;
	}

	async function selectSensor(name: string | null): Promise<void> {
		selectedSensor = selectedSensor === name ? null : name;
		actionError = null;
		try {
			await refreshTicks();
		} catch (caught) {
			actionError = String(caught);
		}
	}

	async function act<Result>(action: () => Promise<Result>): Promise<Result | null> {
		if (busy) return null;
		busy = true;
		actionError = null;
		actionMessage = null;
		try {
			const result: Result = await action();
			refreshing = false;
			await refresh();
			return result;
		} catch (caught) {
			actionError = String(caught);
			return null;
		} finally {
			busy = false;
		}
	}

	async function setStatus(name: string, status: string): Promise<void> {
		await act(() => requestSensorStatus(name, status));
	}

	async function retryDeadLetter(sensorName: string, eventId: string): Promise<void> {
		if (busy) return;
		pendingDeadLetterAction = { eventId, type: 'retry' };
		try {
			const result: DeadLetterActionResult | null = await act(() =>
				requestDeadLetterRetry(sensorName, eventId)
			);
			if (result?.status === 'succeeded') {
				actionMessage = 'Retry succeeded. The event is resolved.';
			} else if (result?.status === 'skipped') {
				actionMessage = 'Retry completed as skipped. The event is resolved.';
			} else if (result !== null) {
				actionError = 'Retry failed. The event remains in Dead letters.';
			}
		} finally {
			pendingDeadLetterAction = null;
		}
	}

	async function skipDeadLetter(
		sensorName: string,
		eventId: string,
		reason: string
	): Promise<void> {
		if (busy) return;
		pendingDeadLetterAction = { eventId, type: 'skip' };
		try {
			const result: DeadLetterActionResult | null = await act(() =>
				requestDeadLetterSkip(sensorName, eventId, reason)
			);
			if (result !== null) {
				actionMessage = 'Event skipped and resolved.';
			}
		} finally {
			pendingDeadLetterAction = null;
		}
	}

	const polling: SensorsPollingResource = createSensorsPollingResource(refresh);

	function start(): () => void {
		return polling.start();
	}

	return {
		get payload() {
			return payload;
		},
		get deadLetters() {
			return deadLetters;
		},
		get selectedSensor() {
			return selectedSensor;
		},
		get ticks() {
			return ticks;
		},
		get loading() {
			return loading;
		},
		get error() {
			return error;
		},
		get actionError() {
			return actionError;
		},
		get actionMessage() {
			return actionMessage;
		},
		get busy() {
			return busy;
		},
		get pendingDeadLetterAction() {
			return pendingDeadLetterAction;
		},
		start,
		selectSensor,
		setStatus,
		retryDeadLetter,
		skipDeadLetter
	};
}
