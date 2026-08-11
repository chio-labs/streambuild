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

export type RunCommandSuggestionGroup = 'Flags' | 'Pipelines' | 'Models' | 'Confirmations';

export type RunCommandSuggestion = {
	value: string;
	primary: string;
	secondary: string;
	group: RunCommandSuggestionGroup;
};

export type RunCommandCompletion = {
	command: string;
	cursor: number;
};

export type ShellToken = {
	value: string;
	start: number;
	end: number;
};

export type ShellTokenization = {
	tokens: ShellToken[];
	error: string | null;
};

export type ActiveShellToken = {
	start: number;
	end: number;
	prefix: string;
	previousToken: string | null;
};
