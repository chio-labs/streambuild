# StreamBuild UI

This SvelteKit application is the frontend served by `stb dev`. Production assets are built into
`src/streambuild/dev_server/static` and included in the Python distribution.

## Local Development

Start the StreamBuild backend from a project directory:

```bash
uv run stb dev
```

Then start Vite in another terminal:

```bash
cd ui
npm ci
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`. Open the URL printed by Vite.

## Checks

```bash
npm run check
npm run verify:lanes
npm run build
```

`npm run shots` is a visual-review screenshot tool, not the pytest browser E2E lane. It expects the
required browser and a reachable backend. Run the packaged browser suite from the repository root
with `make test-browser`.

From the repository root, `make ui-install ui-build` installs dependencies, builds the static
application, and replaces the packaged assets.
