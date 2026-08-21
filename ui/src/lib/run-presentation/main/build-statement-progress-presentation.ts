import type { RunEventFeed } from '$lib/api/types';
import type { StatementProgressPresentation } from '$lib/run-presentation/types';

type StatementProgress = NonNullable<RunEventFeed['statementProgress']>;

export function buildStatementProgressPresentation(
	progress: StatementProgress,
	totalStatements: number | null
): StatementProgressPresentation {
	const totalRows: number = progress.totalRowsApprox ?? 0;
	const readRows: number = progress.readRows ?? 0;
	const credibleTotal: boolean = progress.found && totalRows > 0 && readRows <= totalRows;
	const percentage: number | null = credibleTotal
		? Math.min((readRows / totalRows) * 100, 100)
		: null;
	const rowsPerSecond: number = progress.readRowsPerSecond ?? 0;
	return {
		position:
			totalStatements === null
				? String(progress.statementSequence)
				: `${progress.statementSequence}/${totalStatements}`,
		pendingStatements:
			totalStatements === null
				? null
				: Math.max(totalStatements - progress.statementSequence, 0),
		percentage,
		etaSeconds:
			percentage === null || rowsPerSecond <= 0
				? null
				: Math.max((totalRows - readRows) / rowsPerSecond, 0)
	};
}
