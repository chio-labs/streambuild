export type Theme = 'dark' | 'light';

export type ThemeController = {
	readonly value: Theme;
	toggle(): void;
};
