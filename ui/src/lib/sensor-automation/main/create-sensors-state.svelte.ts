import {
	fetchDeadLetters,
	requestDeadLetterRetry,
	requestDeadLetterSkip
} from '../_api/dead-letters';
import { fetchSensors, fetchSensorTicks } from '../_api/sensor-collection';
import { requestSensorStatus } from '../_api/sensor-status';
import { createSensorsPollingResource } from '../_resources/sensors-polling.resource';
import type {
	DeadLettersPayload,
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
	let busy = $state<boolean>(false);
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

	async function act(action: () => Promise<unknown>): Promise<void> {
		busy = true;
		actionError = null;
		try {
			await action();
			refreshing = false;
			await refresh();
		} catch (caught) {
			actionError = String(caught);
		} finally {
			busy = false;
		}
	}

	async function setStatus(name: string, status: string): Promise<void> {
		await act(() => requestSensorStatus(name, status));
	}

	async function retryDeadLetter(sensorName: string, eventId: string): Promise<void> {
		await act(() => requestDeadLetterRetry(sensorName, eventId));
	}

	async function skipDeadLetter(
		sensorName: string,
		eventId: string,
		reason: string
	): Promise<void> {
		await act(() => requestDeadLetterSkip(sensorName, eventId, reason));
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
		get busy() {
			return busy;
		},
		start,
		selectSensor,
		setStatus,
		retryDeadLetter,
		skipDeadLetter
	};
}
