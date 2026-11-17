/**
 * The web app's service worker (v2 P3-D), scope `/next/`.
 *
 * - Precaches this build's files (hashed, immutable) and answers them from
 *   the cache, so a repeat visit loads the app without the network.
 * - A page load that fails offline gets a small offline page. Pages and data
 *   are never stored: signed-in pages are the visitor's own (`no-store`).
 * - Everything else (API calls, sign-in, Django pages) is left to the
 *   browser untouched.
 * - A new version waits until the visitor reloads from the update prompt
 *   (UpdatePrompt.svelte), so an open tab never loses the files it still uses.
 *
 * Cache Storage is shared with the Django site's worker; this one keeps to
 * `floppy-web-*` caches and that one leaves them alone.
 */
import { self } from '$app/service-worker';
import { assets, immutable } from '$app/manifest';
import { version } from '$app/env';

const PREFIX = 'floppy-web-';
const CACHE = `${PREFIX}${version}`;
const SCOPE = new URL(self.registration.scope);
const PRECACHE = new Set([...immutable, ...assets].map(({ path }) => new URL(path, SCOPE).href));

self.addEventListener('install', (event) => {
	event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll([...PRECACHE])));
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((names) =>
				Promise.all(
					names
						.filter((name) => name.startsWith(PREFIX) && name !== CACHE)
						.map((name) => caches.delete(name))
				)
			)
			.then(() => self.clients.claim())
	);
});

self.addEventListener('message', (event) => {
	if (event.data === 'floppy-web:activate') self.skipWaiting();
});

function offlinePage(): Response {
	const html =
		'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' +
		'<title>Offline · Floppy</title>' +
		'<body style="margin:0;display:grid;place-items:center;min-height:100vh;background:#1c1b22;color:#f8f9fb;font-family:system-ui,sans-serif">' +
		'<main style="max-width:420px;margin:20px;padding:28px;border-radius:22px;text-align:center;background:rgb(180 195 210 / 7.5%);border:1px solid rgb(255 255 255 / 7%)">' +
		'<h1 style="font-size:20px;margin:0 0 8px">You are offline</h1>' +
		'<p style="color:#a2aeb8;margin:0">Floppy will load again once you are connected.</p>' +
		'<p style="margin:16px 0 0"><a href="" style="color:#a9cbff">Try again</a></p></main></body>';
	return new Response(html, {
		status: 503,
		headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' }
	});
}

self.addEventListener('fetch', (event) => {
	const request = event.request;
	if (request.method !== 'GET') return;
	const url = new URL(request.url);
	if (url.origin !== SCOPE.origin) return;

	if (PRECACHE.has(url.href)) {
		event.respondWith(
			caches.open(CACHE).then(async (cache) => (await cache.match(request)) ?? fetch(request))
		);
		return;
	}

	if (request.mode === 'navigate' && url.pathname.startsWith(SCOPE.pathname)) {
		event.respondWith(fetch(request).catch(() => offlinePage()));
	}
});
