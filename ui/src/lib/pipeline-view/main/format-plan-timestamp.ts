export function formatPlanTimestamp(value: string): string {
	const date: Date = new Date(value);
	return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
