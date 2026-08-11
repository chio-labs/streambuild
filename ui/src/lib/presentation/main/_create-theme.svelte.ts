import { browser } from '$app/environment';
import type { Theme, ThemeController } from '$lib/presentation/types';

export function createTheme(): ThemeController {
	let value: Theme = $state(readTheme());

	return {
		get value(): Theme {
			return value;
		},
		toggle(): void {
			value = value === 'dark' ? 'light' : 'dark';
			applyTheme(value);
		}
	};
}

function readTheme(): Theme {
	if (!browser) return 'dark';
	return localStorage.getItem('sb-theme') === 'light' ? 'light' : 'dark';
}

function applyTheme(theme: Theme): void {
	if (!browser) return;
	document.documentElement.classList.toggle('dark', theme === 'dark');
	localStorage.setItem('sb-theme', theme);
}
