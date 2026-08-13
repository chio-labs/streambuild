import ActivityIcon from '@lucide/svelte/icons/activity';
import HistoryIcon from '@lucide/svelte/icons/history';
import LayersIcon from '@lucide/svelte/icons/layers';
import LibraryIcon from '@lucide/svelte/icons/library';
import ListTreeIcon from '@lucide/svelte/icons/list-tree';
import NetworkIcon from '@lucide/svelte/icons/network';
import RadarIcon from '@lucide/svelte/icons/radar';
import RadioIcon from '@lucide/svelte/icons/radio';
import ReplaceIcon from '@lucide/svelte/icons/replace';
import ShieldCheckIcon from '@lucide/svelte/icons/shield-check';
import WorkflowIcon from '@lucide/svelte/icons/workflow';
import type { SidebarNavGroup } from './types';

export const SIDEBAR_NAV_GROUPS: SidebarNavGroup[] = [
	{
		section: 'Flow',
		items: [
			{ label: 'Overview', href: '/', icon: ActivityIcon },
			{ label: 'Lineage', href: '/lineage', icon: NetworkIcon },
			{ label: 'Pipelines', href: '/pipelines', icon: WorkflowIcon },
			{ label: 'Catalog', href: '/catalog', icon: LibraryIcon },
			{ label: 'Sources', href: '/sources', icon: RadioIcon },
			{ label: 'Topics', href: '/topics', icon: ListTreeIcon }
		]
	},
	{
		section: 'Change',
		items: [
			{ label: 'Plan', href: '/plan', icon: ReplaceIcon },
			{ label: 'Deployments', href: '/deployments', icon: LayersIcon },
			{ label: 'Quality', href: '/quality', icon: ShieldCheckIcon },
			{ label: 'Sensors', href: '/sensors', icon: RadarIcon },
			{ label: 'Runs', href: '/runs', icon: HistoryIcon }
		]
	}
];
