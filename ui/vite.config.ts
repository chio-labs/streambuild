import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// UI development runs against a live `sqt dev` backend on :8000. SQT_DEV_API
// overrides the target so several checkouts can iterate on different ports.
const API_TARGET = process.env.SQT_DEV_API ?? 'http://127.0.0.1:8000';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		proxy: { '/api': API_TARGET }
	}
});
