import type { Pipeline, Project } from '$lib/domain/types';
import {
	activeToken,
	collectFlagValues,
	filterSuggestions
} from '$lib/run-command/_helpers/command-tokens';
import { quoteShellToken } from '$lib/run-command/_helpers/shell-tokens';
import { RUN_COMMAND_FLAGS } from '$lib/run-command/constants';
import type { ActiveShellToken, RunCommandSuggestion } from '$lib/run-command/types';

export function runCommandSuggestions(
	raw: string,
	cursor: number,
	project: Project,
	protectedPipelines: Pipeline[]
): RunCommandSuggestion[] {
	const active: ActiveShellToken = activeToken(raw, cursor);
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
