export type Theme = 'dark' | 'light';

export type ThemeController = {
	readonly value: Theme;
	toggle(): void;
};

export type SidebarNavItem = {
	label: string;
	href: string;
	icon: typeof import('@lucide/svelte').Icon;
};

export type SidebarNavGroup = {
	section: string;
	items: SidebarNavItem[];
};

export type UnifiedDiffLineKind = 'header' | 'hunk' | 'add' | 'del' | 'context';

export type UnifiedDiffLine = {
	readonly kind: UnifiedDiffLineKind;
	/** Gutter marker: `+`, `−`, or empty for headers, hunks and context. */
	readonly sign: string;
	/** Line text without its unified-diff prefix column. */
	readonly text: string;
};

export type UnifiedDiff = {
	readonly lines: UnifiedDiffLine[];
	readonly added: number;
	readonly removed: number;
};
