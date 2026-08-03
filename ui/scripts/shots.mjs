/**
 * Screenshot harness for local UI review.
 *
 * Uses playwright-core against the SYSTEM Chrome (no 150MB browser download).
 * Because the app is a pure SPA (ssr = false) there is no server-rendered HTML
 * to inspect, so screenshots + console capture are the only way to verify a
 * page actually rendered.
 *
 *   npm run dev                       # in one shell, serves :5173
 *   npm run shots                     # default route list
 *   npm run shots -- /graph /plan     # explicit routes
 *
 * Env overrides:
 *   CHROME_PATH   explicit browser binary
 *   SHOT_BASE     default http://localhost:5173
 *   SHOT_OUT      default shots/
 *   SHOT_WIDTH    default 1600
 *   SHOT_HEIGHT   default 1000
 *   SHOT_THEME    dark | light   (seeds localStorage before first paint)
 *   SHOT_FULL     1 = full-page capture instead of viewport
 */

import { chromium } from 'playwright-core';
import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const BASE = process.env.SHOT_BASE ?? 'http://localhost:5173';
const OUT_DIR = process.env.SHOT_OUT ?? 'shots';
const WIDTH = Number(process.env.SHOT_WIDTH ?? 1600);
const HEIGHT = Number(process.env.SHOT_HEIGHT ?? 1000);
const THEME = process.env.SHOT_THEME ?? 'dark';
const FULL_PAGE = process.env.SHOT_FULL === '1';

const DEFAULT_ROUTES = ['/'];

const BROWSER_CANDIDATES = [
	process.env.CHROME_PATH,
	'/usr/bin/google-chrome',
	'/usr/bin/google-chrome-stable',
	'/usr/bin/chromium',
	'/usr/bin/chromium-browser',
	'/opt/google/chrome/google-chrome'
].filter(Boolean);

function resolveBrowser() {
	const found = BROWSER_CANDIDATES.find((candidate) => existsSync(candidate));
	if (!found) {
		console.error('No Chrome/Chromium binary found. Tried:');
		for (const candidate of BROWSER_CANDIDATES) console.error(`  ${candidate}`);
		console.error('Set CHROME_PATH to an explicit binary.');
		process.exit(2);
	}
	return found;
}

function slugify(route) {
	const cleaned = route.replace(/^\/+|\/+$/g, '');
	return cleaned === '' ? 'index' : cleaned.replace(/[^a-z0-9]+/gi, '-').toLowerCase();
}

const routes = process.argv.slice(2).length ? process.argv.slice(2) : DEFAULT_ROUTES;

const executablePath = resolveBrowser();
await mkdir(OUT_DIR, { recursive: true });

const browser = await chromium.launch({
	executablePath,
	args: ['--no-sandbox', '--disable-dev-shm-usage', '--force-color-profile=srgb']
});

const context = await browser.newContext({
	viewport: { width: WIDTH, height: HEIGHT },
	deviceScaleFactor: 1,
	colorScheme: THEME === 'light' ? 'light' : 'dark'
});

// app.html reads localStorage('sb-theme') before first paint to avoid a flash.
await context.addInitScript(`try { localStorage.setItem('sb-theme', '${THEME}'); } catch (e) {}`);

let failures = 0;

console.log(`browser   ${executablePath}`);
console.log(`base      ${BASE}`);
console.log(`viewport  ${WIDTH}x${HEIGHT}  theme=${THEME}\n`);

for (const route of routes) {
	const page = await context.newPage();
	const problems = [];

	// Chrome always probes /favicon.ico regardless of <link rel="icon">. Ignoring it
	// keeps real problems visible instead of a 404 on every single page.
	const isNoise = (url) => url.endsWith('/favicon.ico');

	page.on('console', (message) => {
		if (message.type() !== 'error') return;
		const text = message.text();
		if (text.includes('favicon.ico') || text.includes('status of 404')) return;
		problems.push(`console.error  ${text}`);
	});
	page.on('pageerror', (error) => problems.push(`pageerror      ${error.message.split('\n')[0]}`));
	page.on('requestfailed', (request) => {
		if (!isNoise(request.url())) problems.push(`requestfailed  ${request.url()}`);
	});
	page.on('response', (response) => {
		if (response.status() >= 400 && !isNoise(response.url())) {
			problems.push(`http ${response.status()}     ${response.url()}`);
		}
	});

	const target = `${BASE}${route}`;
	let status = 'ok';

	// `load` rather than `networkidle`: a page whose main thread is wedged (e.g. a
	// Svelte 5 effect loop) never reaches networkidle, and we'd lose the console
	// output that actually explains why.
	try {
		const response = await page.goto(target, { waitUntil: 'load', timeout: 15000 });
		if (response && response.status() >= 400) problems.push(`http ${response.status()}`);
	} catch (error) {
		problems.push(`navigation     ${error.message.split('\n')[0]}`);
		status = 'nav-failed';
	}

	// Wait for the app shell, then let dagre layout / fonts / transitions settle.
	// Vite's dependency pre-bundling can force a full reload mid-navigation, so a
	// single blank read is retried once before being reported as a real failure.
	async function settle() {
		await page.waitForSelector('aside', { timeout: 10000 }).catch(() => {});
		await page.waitForTimeout(800);
		return page.evaluate(() => document.body?.innerText?.trim().length ?? 0).catch(() => 0);
	}

	// Optional interaction pass, so stateful UI (collapse, toggles, popovers) can
	// be captured rather than only initial render.
	const clicks = (process.env.SHOT_CLICK ?? '').split(',').map((s) => s.trim()).filter(Boolean);
	for (const selector of clicks) {
		try {
			await page.click(selector, { timeout: 4000 });
			await page.waitForTimeout(450);
		} catch (error) {
			problems.push(`click          ${selector}: ${error.message.split('\n')[0]}`);
		}
	}

	let textLength = await settle();
	if (textLength < 20) {
		await page.reload({ waitUntil: 'load', timeout: 15000 }).catch(() => {});
		textLength = await settle();
	}
	if (textLength < 20) {
		problems.push(`blank page     body text length ${textLength}`);
		status = 'blank';
	}

	const file = path.join(OUT_DIR, `${slugify(route)}-${THEME}.png`);
	await page.screenshot({ path: file, fullPage: FULL_PAGE }).catch((error) => {
		problems.push(`screenshot     ${error.message}`);
	});

	if (problems.length) {
		failures += 1;
		console.log(`✗ ${route.padEnd(28)} ${status}  -> ${file}`);
		for (const problem of problems) console.log(`    ${problem}`);
	} else {
		console.log(`✓ ${route.padEnd(28)} -> ${file}`);
	}

	await page.close();
}

await context.close();
await browser.close();

console.log(`\n${routes.length - failures}/${routes.length} clean`);
process.exit(failures > 0 ? 1 : 0);
