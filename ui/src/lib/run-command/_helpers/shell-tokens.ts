import type { ShellToken, ShellTokenization } from '$lib/run-command/types';

export function shellTokens(raw: string, allowIncomplete: boolean = false): ShellTokenization {
	const tokens: ShellToken[] = [];
	let value: string = '';
	let start: number | null = null;
	let quote: "'" | '"' | null = null;
	let escaped: boolean = false;

	function finish(end: number): void {
		if (start === null) return;
		tokens.push({ value, start, end });
		value = '';
		start = null;
	}

	for (let index: number = 0; index < raw.length; index += 1) {
		const character: string = raw[index];
		if (escaped) {
			value += character;
			escaped = false;
			continue;
		}
		if (quote === "'") {
			if (character === "'") quote = null;
			else value += character;
			continue;
		}
		if (quote === '"') {
			if (character === '"') quote = null;
			else if (character === '\\') escaped = true;
			else value += character;
			continue;
		}
		if (/\s/.test(character)) {
			finish(index);
			continue;
		}
		if (start === null) start = index;
		if (character === "'" || character === '"') quote = character;
		else if (character === '\\') escaped = true;
		else value += character;
	}
	if (!allowIncomplete && (quote !== null || escaped)) {
		return { tokens, error: 'command contains an unterminated quote or escape' };
	}
	if (escaped) value += '\\';
	finish(raw.length);
	return { tokens, error: null };
}

export function quoteShellToken(value: string): string {
	if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(value)) return value;
	return `'${value.replaceAll("'", `'"'"'`)}'`;
}
