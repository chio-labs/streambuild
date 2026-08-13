import { fetchSensorTicks } from '../_api/sensor-collection';
import { msToTimestamp, timestampToMs } from '../_helpers/timeline-scale';
import {
	createWindowFetchDebounce,
	type WindowFetchDebounce
} from '../_resources/window-fetch-debounce.resource';
import type { SensorTick, SensorTicksPayload, TickTimelineState } from '../types';

const MIN_SPAN_MS = 30_000;
const MAX_SPAN_MS = 90 * 24 * 60 * 60 * 1_000;
const MIN_SEED_SPAN_MS = 60_000;
const SEED_PAD_FRACTION = 0.05;
const FETCH_DEBOUNCE_MS = 300;
const WINDOW_TICK_LIMIT = 500;
const ZOOM_SENSITIVITY = 0.0015;

export function createTickTimeline(sensorName: () => string): TickTimelineState {
	let ticks = $state<SensorTick[]>([]);
	let startMs = $state<number>(0);
	let endMs = $state<number>(0);
	let loading = $state<boolean>(false);
	let error = $state<string | null>(null);
	let ready = $state<boolean>(false);
	let defaultStartMs = 0;
	let defaultEndMs = 0;
	const debounce: WindowFetchDebounce = createWindowFetchDebounce(FETCH_DEBOUNCE_MS);
	let fetchToken = 0;

	function initialize(seedTicks: SensorTick[]): void {
		if (ready) return;
		const nowMs: number = Date.now();
		const oldestMs: number = seedTicks.length
			? Math.min(...seedTicks.map((tick) => timestampToMs(tick.startedAt)))
			: nowMs - MIN_SEED_SPAN_MS;
		const spanMs: number = Math.max(nowMs - oldestMs, MIN_SEED_SPAN_MS);
		defaultStartMs = nowMs - spanMs * (1 + SEED_PAD_FRACTION);
		defaultEndMs = nowMs;
		startMs = defaultStartMs;
		endMs = defaultEndMs;
		ticks = seedTicks;
		ready = true;
	}

	function applyWindow(nextStartMs: number, nextEndMs: number): void {
		const nowMs: number = Date.now();
		let nextStart: number = nextStartMs;
		let nextEnd: number = nextEndMs;
		if (nextEnd > nowMs) {
			nextStart -= nextEnd - nowMs;
			nextEnd = nowMs;
		}
		// Fractional milliseconds cannot round-trip through warehouse timestamps.
		startMs = Math.round(nextStart);
		endMs = Math.round(nextEnd);
		scheduleFetch();
	}

	function zoomAt(fraction: number, deltaY: number): void {
		if (!ready) return;
		const spanMs: number = endMs - startMs;
		const nextSpanMs: number = Math.min(
			Math.max(spanMs * Math.exp(deltaY * ZOOM_SENSITIVITY), MIN_SPAN_MS),
			MAX_SPAN_MS
		);
		const anchorMs: number = startMs + spanMs * fraction;
		applyWindow(anchorMs - nextSpanMs * fraction, anchorMs + nextSpanMs * (1 - fraction));
	}

	function panBy(fraction: number): void {
		if (!ready) return;
		const shiftMs: number = (endMs - startMs) * fraction;
		applyWindow(startMs + shiftMs, endMs + shiftMs);
	}

	function reset(): void {
		if (!ready) return;
		applyWindow(defaultStartMs, defaultEndMs);
	}

	function scheduleFetch(): void {
		loading = true;
		debounce.schedule(() => void fetchWindow());
	}

	async function fetchWindow(): Promise<void> {
		const token: number = ++fetchToken;
		try {
			const payload: SensorTicksPayload = await fetchSensorTicks(sensorName(), undefined, {
				after: msToTimestamp(startMs),
				before: msToTimestamp(endMs),
				limit: WINDOW_TICK_LIMIT
			});
			if (token !== fetchToken) return;
			ticks = payload.ticks;
			error = null;
		} catch (caught) {
			if (token !== fetchToken) return;
			error = String(caught);
		} finally {
			if (token === fetchToken) loading = false;
		}
	}

	function stop(): void {
		debounce.cancel();
		fetchToken += 1;
	}

	return {
		get ticks() {
			return ticks;
		},
		get startMs() {
			return startMs;
		},
		get endMs() {
			return endMs;
		},
		get loading() {
			return loading;
		},
		get error() {
			return error;
		},
		get ready() {
			return ready;
		},
		initialize,
		zoomAt,
		panBy,
		reset,
		stop
	};
}
