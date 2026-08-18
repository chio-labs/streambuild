/**
 * Cap error text for display without ever splitting a UTF-8 code point.
 *
 * Errors (unlike streaming logs) put the useful part — the message and failing
 * expression — at the *front*, so we keep the head and drop the tail. Copy and
 * download always operate on the full, uncapped string held by the caller.
 */

export interface CappedText {
	/** The head slice safe to render in the DOM. */
	text: string;
	/** Bytes dropped from the tail; zero when nothing was capped. */
	truncatedBytes: number;
	isTruncated: boolean;
}

/** 256 KB: absurdly large for a message, still safe for the DOM. */
export const DEFAULT_ERROR_CAP_BYTES = 256 * 1024;

const encoder = new TextEncoder();

export function capErrorText(
	text: string,
	limitBytes: number = DEFAULT_ERROR_CAP_BYTES
): CappedText {
	const totalBytes: number = encoder.encode(text).length;
	if (totalBytes <= limitBytes) {
		return { text, truncatedBytes: 0, isTruncated: false };
	}
	let keptBytes: number = 0;
	let endIndex: number = 0;
	for (const codePoint of text) {
		const codePointBytes: number = encoder.encode(codePoint).length;
		if (keptBytes + codePointBytes > limitBytes) break;
		keptBytes += codePointBytes;
		endIndex += codePoint.length;
	}
	return {
		text: text.slice(0, endIndex),
		truncatedBytes: totalBytes - keptBytes,
		isTruncated: true
	};
}

export function formatByteSize(bytes: number): string {
	if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
	return `${bytes} B`;
}
