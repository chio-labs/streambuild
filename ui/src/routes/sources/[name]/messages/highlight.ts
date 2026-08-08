/** Split text into hit/miss segments for the active filter criteria. */

export type HighlightSegment = { text: string; hit: boolean };

function splitOne(text: string, term: string): HighlightSegment[] {
	const segments: HighlightSegment[] = [];
	let position = 0;
	let found = text.indexOf(term);
	while (found >= 0) {
		if (found > position) segments.push({ text: text.slice(position, found), hit: false });
		segments.push({ text: term, hit: true });
		position = found + term.length;
		found = text.indexOf(term, position);
	}
	if (position < text.length) segments.push({ text: text.slice(position), hit: false });
	return segments;
}

/** Matching is case-sensitive, mirroring the server-side position() semantics. */
export function splitByTerms(text: string, terms: string[]): HighlightSegment[] {
	let segments: HighlightSegment[] = [{ text, hit: false }];
	for (const term of terms.filter((candidate) => candidate.length > 0)) {
		segments = segments.flatMap((segment) =>
			segment.hit ? [segment] : splitOne(segment.text, term)
		);
	}
	return segments;
}
