import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// UI development runs against a live `stb dev` backend on :8000. STB_DEV_API
// overrides the target so several checkouts can iterate on different ports.
const API_TARGET = process.env.STB_DEV_API ?? 'http://127.0.0.1:8000';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		proxy: { '/api': API_TARGET }
	}
});
