import type { AnchorState, RefType, ReplayRole } from '$lib/domain/types';

export const REPLAY_COLUMN_BY_ROLE: Record<ReplayRole, string> = {
	partition: '_replay_partition',
	offset: '_replay_offset',
	timestamp: '_replay_timestamp',
	landed_at: '_replay_landed_at',
	cursor: '_replay_cursor'
};

export const ANCHOR_REASON: Record<AnchorState, string> = {
	eligible: 'Replay anchor — a replay can start here',
	aggregate: 'Not an anchor: aggregate model, replay predicates go on its input',
	mutable_ref: 'Not an anchor: has a mutable side reference',
	never: 'Not an anchor: MODEL() sets replay_anchor never',
	lineage_loss: 'Not an anchor: replay lineage columns are not projected through',
	view: 'Terminal views take no part in replay'
};

export const REF_TYPE_LABEL: Record<RefType, string> = {
	driving_input: 'driving input',
	reference: 'reference',
	mutable_reference: 'mutable reference'
};

export const OWNERSHIP_LABEL: Record<string, string> = {
	direct: 'owned by StreamBuild (direct)',
	unmanaged: 'not owned by StreamBuild',
	conflicted: 'owned by another mode',
	absent: 'does not exist yet',
	virtual_environment: 'owned by a virtual environment'
};
