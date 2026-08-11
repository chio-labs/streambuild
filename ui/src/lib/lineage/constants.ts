import type { NodeFieldSet } from '$lib/lineage/types';

export const NODE_FIELD_LABELS: Record<keyof NodeFieldSet, string> = {
	kind: 'Engine / kind',
	status: 'Status rail',
	relation: 'Relation name',
	anchor: 'Replay anchor',
	checks: 'Audit results',
	rows: 'Row count',
	rate: 'Ingest rate'
};
