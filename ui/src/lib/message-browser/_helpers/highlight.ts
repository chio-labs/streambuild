import type { HighlightSegment } from '$lib/message-browser/types';

export function splitByTerms(text: string, terms: string[]): HighlightSegment[] {
	let segments: HighlightSegment[] = [{ text, hit: false }];
	for (const term of terms.filter((candidate) => candidate.length > 0)) {
		segments = segments.flatMap((segment) =>
			segment.hit ? [segment] : splitOne(segment.text, term)
		);
	}
	return segments;
}

function splitOne(text: string, term: string): HighlightSegment[] {
	const segments: HighlightSegment[] = [];
	let position: number = 0;
	let found: number = text.indexOf(term);
	while (found >= 0) {
		if (found > position) segments.push({ text: text.slice(position, found), hit: false });
		segments.push({ text: term, hit: true });
		position = found + term.length;
		found = text.indexOf(term, position);
	}
	if (position < text.length) segments.push({ text: text.slice(position), hit: false });
	return segments;
}
