import type { NodeTypes } from '@xyflow/svelte';
import CollapsedGroupNode from '$lib/presentation/components/lineage/collapsed-group-node.svelte';
import GroupNode from '$lib/presentation/components/lineage/group-node.svelte';
import LaneNode from '$lib/presentation/components/lineage/lane-node.svelte';
import StreamNode from '$lib/presentation/components/lineage/stream-node.svelte';

export const LINEAGE_NODE_TYPES: NodeTypes = {
	stream: StreamNode,
	group: GroupNode,
	collapsedGroup: CollapsedGroupNode,
	lane: LaneNode
};
