import type { NodeFieldController, NodeFieldSet } from '$lib/lineage/types';

const STORAGE_KEY: string = 'sb-node-fields';
const DEFAULTS: NodeFieldSet = {
	kind: true,
	status: true,
	relation: true,
	anchor: true,
	checks: true,
	rows: false,
	rate: true
};

export function createNodeFieldsState(): NodeFieldController {
	let value: NodeFieldSet = $state(loadNodeFields());

	function persist(): void {
		if (typeof localStorage === 'undefined') return;
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
		} catch {
			return;
		}
	}

	return {
		get value(): NodeFieldSet {
			return value;
		},
		toggle(field: keyof NodeFieldSet): void {
			value = { ...value, [field]: !value[field] };
			persist();
		},
		reset(): void {
			value = { ...DEFAULTS };
			persist();
		}
	};
}

function loadNodeFields(): NodeFieldSet {
	if (typeof localStorage === 'undefined') return { ...DEFAULTS };
	try {
		const raw: string | null = localStorage.getItem(STORAGE_KEY);
		if (!raw) return { ...DEFAULTS };
		return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<NodeFieldSet>) };
	} catch {
		return { ...DEFAULTS };
	}
}
