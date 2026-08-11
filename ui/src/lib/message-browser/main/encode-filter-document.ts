import { encodeFilterDocument as encode } from '$lib/message-browser/_helpers/filter-document';
import type { MessageFilterDocument } from '$lib/message-browser/types';

export function encodeFilterDocument(document: MessageFilterDocument): string | null {
	return encode(document);
}
