// SPA mode: no SSR, no prerender. All data is fetched client-side from the
// Python Hub API. This makes the build a static bundle served by the backend.
export const ssr = false;
export const prerender = false;
export const trailingSlash = 'never';
