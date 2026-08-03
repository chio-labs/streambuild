/**
 * Which optional fields render on graph nodes. Persisted to localStorage.
 *
 * `main` called these "Node fields" deliberately (not Dagster's "facets") and the
 * name still fits, so it stays. The field SET is StreamBuild's own.
 */

const STORAGE_KEY = 'sb-node-fields';

export type NodeFieldSet = {
	kind: boolean;
	status: boolean;
	/** The physical relation name — `tbl__orders`, `mv__orders`. */
	relation: boolean;
	/** Replay anchor eligibility. */
	anchor: boolean;
	checks: boolean;
	rows: boolean;
	/** Ingest rate, sources only. */
	rate: boolean;
};

const DEFAULTS: NodeFieldSet = {
	kind: true,
	status: true,
	relation: true,
	anchor: true,
	checks: true,
	rows: false,
	rate: true
};

export const NODE_FIELD_LABELS: Record<keyof NodeFieldSet, string> = {
	kind: 'Engine / kind',
	status: 'Status rail',
	relation: 'Relation name',
	anchor: 'Replay anchor',
	checks: 'Audit results',
	rows: 'Row count',
	rate: 'Ingest rate'
};

function load(): NodeFieldSet {
	if (typeof localStorage === 'undefined') return { ...DEFAULTS };
	try {
		const raw: string | null = localStorage.getItem(STORAGE_KEY);
		if (!raw) return { ...DEFAULTS };
		return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<NodeFieldSet>) };
	} catch {
		return { ...DEFAULTS };
	}
}

class NodeFieldStore {
	value: NodeFieldSet = $state(load());

	toggle(field: keyof NodeFieldSet): void {
		this.value = { ...this.value, [field]: !this.value[field] };
		this.persist();
	}

	reset(): void {
		this.value = { ...DEFAULTS };
		this.persist();
	}

	private persist(): void {
		if (typeof localStorage === 'undefined') return;
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(this.value));
		} catch {
			// Non-fatal: preferences are a convenience, not state.
		}
	}
}

export const nodeFields: NodeFieldStore = new NodeFieldStore();

export function enabledFieldCount(): number {
	return Object.values(nodeFields.value).filter(Boolean).length;
}
