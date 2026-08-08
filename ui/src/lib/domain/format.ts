/**
 * Formatting helpers. All relative times are computed against an explicit
 * reference instant (the project's `capturedAt`) rather than `Date.now()`, so
 * the UI is deterministic and screenshots are stable.
 */

const MS_PER_SECOND = 1000;
const MS_PER_MINUTE = 60 * MS_PER_SECOND;
const MS_PER_HOUR = 60 * MS_PER_MINUTE;
const MS_PER_DAY = 24 * MS_PER_HOUR;

export function formatInteger(value: number): string {
	return value.toLocaleString('en-US');
}

/** Compact row counts for dense tables: 41.2M, 118.4M, 5.4k. */
export function formatCompact(value: number): string {
	if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
	if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
	if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
	return String(value);
}

export function formatBytes(bytes: number): string {
	if (bytes <= 0) return '—';
	const units: string[] = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
	let value = bytes;
	let unit = 0;
	while (value >= 1024 && unit < units.length - 1) {
		value /= 1024;
		unit += 1;
	}
	return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

/** Sub-minute precision matters for streaming lag, so seconds stay visible. */
export function formatDuration(seconds: number): string {
	if (!Number.isFinite(seconds)) return '—';
	if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
	if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)}s`;
	if (seconds < MS_PER_HOUR / MS_PER_SECOND) {
		const minutes = Math.floor(seconds / 60);
		const rest = Math.round(seconds % 60);
		return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
	}
	if (seconds < MS_PER_DAY / MS_PER_SECOND) {
		const hours = Math.floor(seconds / 3600);
		const minutes = Math.round((seconds % 3600) / 60);
		return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
	}
	const days = Math.floor(seconds / 86400);
	const hours = Math.round((seconds % 86400) / 3600);
	return hours ? `${days}d ${hours}h` : `${days}d`;
}

/** Whole-day spans, used for retention and coverage tracks. */
export function formatDaySpan(days: number): string {
	if (days >= 365) {
		const years = days / 365;
		return `${years.toFixed(years >= 10 ? 0 : 1)}y`;
	}
	if (days >= 1) return `${Math.round(days)}d`;
	return formatDuration(days * 86400);
}

/**
 * Every timestamp in the system is UTC, but warehouse strings arrive zone-less
 * ('2026-08-04 12:34:56.789'). Bare `new Date()` reads those as browser-local
 * time, shifting comparisons by the UTC offset — which made fresh check
 * results render as 'in the future'. Normalize before parsing.
 */
export function parseUtc(instant: string): Date {
	const isoShaped = instant.includes('T') ? instant : instant.replace(' ', 'T');
	const zoned = /(?:[Zz]|[+-]\d\d:?\d\d)$/.test(isoShaped) ? isoShaped : `${isoShaped}Z`;
	return new Date(zoned);
}

export function millisBetween(from: string, to: string): number {
	return parseUtc(to).getTime() - parseUtc(from).getTime();
}

export function secondsBetween(from: string, to: string): number {
	return millisBetween(from, to) / MS_PER_SECOND;
}

export function daysBetween(from: string, to: string): number {
	return millisBetween(from, to) / MS_PER_DAY;
}

/** "2s ago", "4h 12m ago". `null` renders as an em dash. */
export function formatAgo(instant: string | null, reference: string): string {
	if (!instant) return '—';
	const seconds = secondsBetween(instant, reference);
	if (seconds < 0) return 'in the future';
	if (seconds < 1) return 'just now';
	return `${formatDuration(seconds)} ago`;
}

/** Wall-clock time only — for dense tables where the date is implied. */
export function formatClock(instant: string | null): string {
	if (!instant) return '—';
	return parseUtc(instant).toISOString().slice(11, 19);
}

/** `2026-08-02 12:04:31` — no timezone suffix; the warehouse timezone is stated once. */
export function formatTimestamp(instant: string | null): string {
	if (!instant) return '—';
	return parseUtc(instant).toISOString().slice(0, 19).replace('T', ' ');
}

export function formatDate(instant: string | null): string {
	if (!instant) return '—';
	return parseUtc(instant).toISOString().slice(0, 10);
}

/** `2026-08-02T12:04` — the value shape an `<input type="datetime-local">` wants. */
export function toDateTimeLocal(instant: string): string {
	return parseUtc(instant).toISOString().slice(0, 16);
}

export function fromDateTimeLocal(value: string): string {
	return new Date(`${value}:00.000Z`).toISOString();
}

export function formatRate(rowsPerSecond: number): string {
	if (rowsPerSecond >= 1000) return `${(rowsPerSecond / 1000).toFixed(1)}k/s`;
	if (rowsPerSecond >= 1) return `${Math.round(rowsPerSecond)}/s`;
	if (rowsPerSecond <= 0) return 'idle';
	return `${rowsPerSecond.toFixed(1)}/s`;
}

export function formatPercent(fraction: number): string {
	return `${Math.round(fraction * 100)}%`;
}

/** Compact graph labels show the engine family; details retain the complete expression. */
export function formatEngineFamily(engine: string | null): string {
	if (engine === null) return 'TABLE';
	const argumentStart = engine.indexOf('(');
	return (argumentStart === -1 ? engine : engine.slice(0, argumentStart)).trim() || 'TABLE';
}

/** Clamp helper used by every track/slider geometry calculation. */
export function clamp(value: number, min: number, max: number): number {
	return Math.min(Math.max(value, min), max);
}
