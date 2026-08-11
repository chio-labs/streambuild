import { decodeFilterDocument as decode } from '$lib/message-browser/_helpers/filter-document';
import type { MessageFilterDocument } from '$lib/message-browser/types';

export function decodeFilterDocument(encoded: string | null): MessageFilterDocument {
	return decode(encoded);
}
