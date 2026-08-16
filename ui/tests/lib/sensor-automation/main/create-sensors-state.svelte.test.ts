import { describe, expect, it, vi } from 'vitest';

import type { SensorsPayload, SensorsState } from '../../../../src/lib/sensor-automation/types';

const requests = vi.hoisted(() => ({
	fetchSensors: vi.fn(),
	fetchSensorTicks: vi.fn(),
	fetchDeadLetters: vi.fn(),
	requestSensorStatus: vi.fn(),
	requestDeadLetterRetry: vi.fn(),
	requestDeadLetterSkip: vi.fn()
}));

vi.mock('../../../../src/lib/sensor-automation/_api/sensor-collection', () => ({
	fetchSensors: requests.fetchSensors,
	fetchSensorTicks: requests.fetchSensorTicks
}));
vi.mock('../../../../src/lib/sensor-automation/_api/sensor-status', () => ({
	requestSensorStatus: requests.requestSensorStatus
}));
vi.mock('../../../../src/lib/sensor-automation/_api/dead-letters', () => ({
	fetchDeadLetters: requests.fetchDeadLetters,
	requestDeadLetterRetry: requests.requestDeadLetterRetry,
	requestDeadLetterSkip: requests.requestDeadLetterSkip
}));
vi.mock('../../../../src/lib/sensor-automation/_resources/sensors-polling.resource', () => ({
	createSensorsPollingResource: vi.fn((refresh: () => Promise<void>) => ({
		start: () => {
			void refresh();
			return vi.fn();
		},
		stop: vi.fn()
	}))
}));

import { createSensorsState } from '../../../../src/lib/sensor-automation/main/create-sensors-state.svelte';

const payload: SensorsPayload = {
	sensors: [
		{
			name: 'quality_alerts',
			kind: 'event',
			description: 'Alert on audit transitions.',
			file: 'sensors/quality.py',
			fingerprint: 'abc',
			defaultStatus: 'stopped',
			effectiveStatus: 'stopped',
			override: null,
			retryPolicy: { maxAttempts: 3, backoffSeconds: 30 },
			timeoutSeconds: 60,
			lastTick: null,
			eventType: 'AuditCompleted'
		}
	],
	deadLetterCount: 0,
	health: {
		state: 'idle',
		consecutiveErrors: 0,
		latestError: null,
		backoffSeconds: 0,
		nextTickSeconds: 10,
		lastSuccessfulTick: null,
		lastEvaluatedCount: 0,
		leaseHeld: true
	}
};

describe('sensors state', () => {
	it('given sensors and dead letters when started then the facade exposes both', async () => {
		requests.fetchSensors.mockResolvedValue(payload);
		requests.fetchDeadLetters.mockResolvedValue({ deadLetters: [] });
		const state: SensorsState = createSensorsState();

		state.start();
		await vi.waitFor(() => expect(state.loading).toBe(false));

		expect(state.payload).toEqual(payload);
		expect(state.deadLetters).toEqual([]);
		expect(state.error).toBeNull();
	});

	it('given a status change when applied then the collection is refreshed', async () => {
		requests.fetchSensors.mockResolvedValue(payload);
		requests.fetchDeadLetters.mockResolvedValue({ deadLetters: [] });
		requests.requestSensorStatus.mockResolvedValue({
			sensorName: 'quality_alerts',
			status: 'running'
		});
		const state: SensorsState = createSensorsState();
		state.start();
		await vi.waitFor(() => expect(state.loading).toBe(false));

		await state.setStatus('quality_alerts', 'running');

		expect(requests.requestSensorStatus).toHaveBeenCalledWith('quality_alerts', 'running');
		expect(requests.fetchSensors.mock.calls.length).toBeGreaterThan(1);
		expect(state.actionError).toBeNull();
	});

	it('given a forbidden action when applied then the structured error is surfaced', async () => {
		requests.fetchSensors.mockResolvedValue(payload);
		requests.fetchDeadLetters.mockResolvedValue({ deadLetters: [] });
		requests.requestSensorStatus.mockRejectedValue(
			new Error('Sensor automation management is not permitted')
		);
		const state: SensorsState = createSensorsState();
		state.start();
		await vi.waitFor(() => expect(state.loading).toBe(false));

		await state.setStatus('quality_alerts', 'running');

		expect(state.actionError).toContain('not permitted');
	});

	it('given a selected sensor when toggled then its tick history loads and clears', async () => {
		requests.fetchSensors.mockResolvedValue(payload);
		requests.fetchDeadLetters.mockResolvedValue({ deadLetters: [] });
		requests.fetchSensorTicks.mockResolvedValue({
			sensorName: 'quality_alerts',
			ticks: [
				{
					tickId: 't1',
					sensorName: 'quality_alerts',
					definitionFingerprint: 'abc',
					kind: 'event',
					eventId: 'e1',
					eventKind: 'AuditCompleted',
					attempt: 1,
					status: 'succeeded',
					startedAt: '2024-01-01 00:00:01.000',
					completedAt: '2024-01-01 00:00:02.000',
					errorMessage: null,
					skipReason: null,
					cursor: null
				}
			]
		});
		const state: SensorsState = createSensorsState();
		state.start();
		await vi.waitFor(() => expect(state.loading).toBe(false));

		await state.selectSensor('quality_alerts');
		expect(state.selectedSensor).toBe('quality_alerts');
		expect(state.ticks).toHaveLength(1);

		await state.selectSensor('quality_alerts');
		expect(state.selectedSensor).toBeNull();
		expect(state.ticks).toHaveLength(0);
	});
});
