import type { ReconstructionCoverage, Source } from '$lib/domain/types';
import { parseUtc } from '$lib/formatting/main/parse-utc';

export function sourceDomainFrom(
	source: Source | undefined,
	coverage: ReconstructionCoverage[],
	capturedAt: string
): string {
	const instants: (string | null)[] = [
		source?.live.oldestEventAt || null,
		...coverage.map((row) => row.heldFrom)
	];
	const candidates: number[] = instants
		.filter((instant): instant is string => Boolean(instant))
		.map((instant) => parseUtc(instant).getTime())
		.filter((milliseconds) => Number.isFinite(milliseconds));
	if (candidates.length === 0) return capturedAt;
	return new Date(Math.min(...candidates)).toISOString();
}
