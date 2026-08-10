import { createServer } from 'vite';

const vite = await createServer({
	configFile: false,
	optimizeDeps: { noDiscovery: true },
	server: { middlewareMode: true },
	appType: 'custom'
});

try {
	await vite.ssrLoadModule('/scripts/verify-lane-order.ts');
} finally {
	await vite.close();
}
