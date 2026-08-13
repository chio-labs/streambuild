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
