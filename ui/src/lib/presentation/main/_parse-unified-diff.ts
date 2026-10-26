import type { UnifiedDiff, UnifiedDiffLine } from '$lib/presentation/types';

const FILE_HEADER_PREFIXES: readonly string[] = ['---', '+++'];
const FILE_HEADER_LINE_COUNT: number = 2;

/**
 * Classify a server-rendered unified diff line by line. Only the first two `---`/`+++` lines
 * before the first hunk are file headers; anywhere else they are removed or added content.
 */
export function parseUnifiedDiff(text: string | null | undefined): UnifiedDiff {
	if (!text) return { lines: [], added: 0, removed: 0 };
	const lines: UnifiedDiffLine[] = [];
	let inHunk: boolean = false;
	let headerCount: number = 0;
	let added: number = 0;
	let removed: number = 0;
	for (const raw of text.replace(/\r?\n$/, '').split(/\r?\n/)) {
		if (raw.startsWith('@@')) {
			inHunk = true;
			lines.push({ kind: 'hunk', sign: '', text: raw });
		} else if (
			!inHunk &&
			headerCount < FILE_HEADER_LINE_COUNT &&
			FILE_HEADER_PREFIXES.some((prefix) => raw.startsWith(prefix))
		) {
			headerCount += 1;
			lines.push({ kind: 'header', sign: '', text: raw });
		} else if (raw.startsWith('+')) {
			added += 1;
			lines.push({ kind: 'add', sign: '+', text: raw.slice(1) });
		} else if (raw.startsWith('-')) {
			removed += 1;
			lines.push({ kind: 'del', sign: '−', text: raw.slice(1) });
		} else {
			lines.push({ kind: 'context', sign: '', text: raw.startsWith(' ') ? raw.slice(1) : raw });
		}
	}
	return { lines, added, removed };
}
