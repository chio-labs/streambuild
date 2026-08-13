import type { SensorTick } from '../types';

export function describeTick(tick: SensorTick): string {
	if (tick.errorMessage) return tick.errorMessage;
	if (tick.skipReason) return `skipped: ${tick.skipReason}`;
	if (tick.cursor) return `cursor: ${tick.cursor}`;
	return '';
}
