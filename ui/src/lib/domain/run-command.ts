import type { Pipeline, Project } from '$lib/domain/types';

export type ParsedRunCommand = {
	selectors: string[];
	startTime: string | null;
	confirmations: string[];
	error: string | null;
};

export type RunCommandFlag = {
	flag: string;
	hint: string;
	description: string;
};

export type RunCommandSuggestion = {
	value: string;
	primary: string;
	secondary: string;
	group: 'Flags' | 'Pipelines' | 'Models' | 'Confirmations';
};

export const RUN_COMMAND_FLAGS: RunCommandFlag[] = [
	{ flag: '--select', hint: '<model | pipeline:name>', description: 'Limit the rebuild scope' },
	{
		flag: '--start-time',
		hint: '<YYYY-MM-DDTHH:MM:SSZ>',
		description: 'Bound the replay window'
	},
	{ flag: '--confirm', hint: '<word>', description: 'Confirm a protected pipeline' }
];

const PINNED_CONTEXT_FLAGS: string[] = [
	'--project-dir',
	'--target',
	'--vars',
	'--host',
	'--port',
	'--username',
	'--password',
	'--database'
];

export function parseRunCommand(raw: string, target: string): ParsedRunCommand {
	const tokenized = shellTokens(raw);
	if (tokenized.error !== null) return commandError(tokenized.error);
	const tokens: string[] = tokenized.tokens.map((token) => token.value);
	if (tokens[0] !== 'stb' || tokens[1] !== 'build') {
		return commandError('command must start with `stb build`');
	}
	const selectors: string[] = [];
	const confirmations: string[] = [];
	let startTime: string | null = null;
	let index: number = 2;
	while (index < tokens.length) {
		const token: string = tokens[index];
		const pinnedFlag: string | undefined = PINNED_CONTEXT_FLAGS.find(
			(flag) => token === flag || token.startsWith(`${flag}=`)
		);
		if (pinnedFlag !== undefined) {
			return commandError(
				`${pinnedFlag} is fixed by stb dev and cannot be overridden from the UI (target ${target})`
			);
		}
		if (token === '--select' && tokens[index + 1]) {
			selectors.push(tokens[index + 1]);
			index += 2;
		} else if (token === '--start-time' && tokens[index + 1]) {
			startTime = tokens[index + 1];
			index += 2;
		} else if (token === '--confirm' && tokens[index + 1]) {
			confirmations.push(tokens[index + 1]);
			index += 2;
		} else if (token === '--auto-approve' || token === '--events') {
			index += 1;
		} else {
			return commandError(
				`unsupported token '${token}' - the UI accepts --select, --start-time, and --confirm`
			);
		}
	}
	if (startTime !== null && selectors.length === 0) {
		return commandError('--start-time requires --select');
	}
	return { selectors, startTime, confirmations, error: null };
}

export function runCommandSuggestions(
	raw: string,
	cursor: number,
	project: Project,
	protectedPipelines: Pipeline[]
): RunCommandSuggestion[] {
	const active = activeToken(raw, cursor);
	const needle: string = active.prefix.toLowerCase();
	if (active.previousToken === '--select') {
		const selected: Set<string> = new Set(collectFlagValues(raw, '--select'));
		const pipelines: RunCommandSuggestion[] = project.pipelines
			.map((pipeline) => ({
				value: quoteShellToken(`pipeline:${pipeline.name}`),
				primary: `pipeline:${pipeline.name}`,
				secondary: `${pipeline.models.length} models`,
				group: 'Pipelines' as const
			}))
			.filter((option) => !selected.has(option.primary));
		const models: RunCommandSuggestion[] = project.models
			.map((model) => ({
				value: quoteShellToken(model.name),
				primary: model.name,
				secondary: model.pipeline,
				group: 'Models' as const
			}))
			.filter((option) => !selected.has(option.primary));
		return filterSuggestions([...pipelines, ...models], needle);
	}
	if (active.previousToken === '--confirm') {
		const confirmed: Set<string> = new Set(collectFlagValues(raw, '--confirm'));
		const seen: Set<string> = new Set();
		return filterSuggestions(
			protectedPipelines.flatMap((pipeline): RunCommandSuggestion[] => {
				const value: string = pipeline.protection?.confirmation ?? '';
				if (value === '' || confirmed.has(value) || seen.has(value)) return [];
				seen.add(value);
				return [
					{
						value,
						primary: value,
						secondary: pipeline.name,
						group: 'Confirmations'
					}
				];
			}),
			needle
		);
	}
	if (active.prefix.startsWith('--')) {
		return RUN_COMMAND_FLAGS.filter((item) => item.flag.startsWith(active.prefix)).map((item) => ({
			value: item.flag,
			primary: item.flag,
			secondary: item.description,
			group: 'Flags'
		}));
	}
	return [];
}

export function completeRunCommand(
	raw: string,
	cursor: number,
	value: string
): { command: string; cursor: number } {
	const active = activeToken(raw, cursor);
	const before: string = raw.slice(0, active.start);
	const after: string = raw.slice(active.end);
	const separator: string = /^\s/.test(after) ? '' : ' ';
	const command: string = `${before}${value}${separator}${after}`;
	return {
		command,
		cursor: before.length + value.length + (separator === '' ? 1 : separator.length)
	};
}

function commandError(error: string): ParsedRunCommand {
	return { selectors: [], startTime: null, confirmations: [], error };
}

function activeToken(
	raw: string,
	cursor: number
): { start: number; end: number; prefix: string; previousToken: string | null } {
	const boundedCursor: number = Math.max(0, Math.min(cursor, raw.length));
	const tokens: ShellToken[] = shellTokens(raw, true).tokens;
	const current: ShellToken | undefined = tokens.find(
		(token) => boundedCursor >= token.start && boundedCursor <= token.end
	);
	const start: number = current?.start ?? boundedCursor;
	const end: number = current?.end ?? boundedCursor;
	const previous: ShellToken | undefined = tokens.filter((token) => token.end <= start).at(-1);
	const prefixTokens: ShellToken[] = shellTokens(raw.slice(start, boundedCursor), true).tokens;
	return {
		start,
		end,
		prefix: prefixTokens[0]?.value ?? '',
		previousToken: previous?.value ?? null
	};
}

function collectFlagValues(raw: string, flag: string): string[] {
	const tokens: string[] = shellTokens(raw, true).tokens.map((token) => token.value);
	return tokens.flatMap((token, index) => (token === flag && tokens[index + 1] ? [tokens[index + 1]] : []));
}

function filterSuggestions(
	options: RunCommandSuggestion[],
	needle: string
): RunCommandSuggestion[] {
	return options
		.filter(
			(option) =>
				needle === '' ||
				option.primary.toLowerCase().includes(needle) ||
				option.secondary.toLowerCase().includes(needle)
		)
		.slice(0, 12);
}

type ShellToken = {
	value: string;
	start: number;
	end: number;
};

function shellTokens(
	raw: string,
	allowIncomplete: boolean = false
): { tokens: ShellToken[]; error: string | null } {
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

function quoteShellToken(value: string): string {
	if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(value)) return value;
	return `'${value.replaceAll("'", `'"'"'`)}'`;
}
