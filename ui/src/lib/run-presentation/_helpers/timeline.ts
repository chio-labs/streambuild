import type { TimelineEvent } from '../types';

export function buildTimeline<T extends TimelineEvent>(
	events: T[],
	running: boolean,
	limit: number = 400
): T[] {
	const completedStatements: Map<number, number> = new Map();
	const completedAudits: Map<string, number> = new Map();
	const timeline: T[] = [];

	for (let index: number = events.length - 1; index >= 0 && timeline.length < limit; index -= 1) {
		const event: T = events[index];
		if (event.event === 'run_heartbeat') continue;

		if (event.event === 'statement_completed' && event.statementSequence !== undefined) {
			increment(completedStatements, event.statementSequence);
		} else if (event.event === 'audit_completed' && event.stepId != null) {
			increment(completedAudits, event.stepId);
		} else if (event.event === 'statement_started') {
			if (!running || consume(completedStatements, event.statementSequence)) continue;
		} else if (event.event === 'audit_started') {
			if (!running || consume(completedAudits, event.stepId ?? undefined)) continue;
		}

		timeline.push(event);
	}

	return timeline;
}

function increment<K>(counts: Map<K, number>, key: K): void {
	counts.set(key, (counts.get(key) ?? 0) + 1);
}

function consume<K>(counts: Map<K, number>, key: K | undefined): boolean {
	if (key === undefined) return false;
	const count: number = counts.get(key) ?? 0;
	if (count === 0) return false;
	if (count === 1) counts.delete(key);
	else counts.set(key, count - 1);
	return true;
}
