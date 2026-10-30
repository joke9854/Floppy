const CACHE_NAME = "floppy-v2";
// A6: the last Home a signed-in user loaded, shown when a navigation fails
// offline. Any /accounts/ page (sign-in, sign-out) deletes it, so the private
// copy does not outlive the session on a shared device.
const PAGES_CACHE = "floppy-pages-v1";
const HOME_PATH = "/";
// App routes the offline shell leaves alone (API, OAuth, admin, static).
const PASS_THROUGH_PREFIXES = ["/api/", "/o/", "/admin/", "/static/"];
const urlsToCache = [
  "/static/css/main.css",
  "/static/favicon/android-chrome-192x192.png",
  "/static/favicon/android-chrome-512x512.png",
  "/static/fonts/roboto-flex.woff2",
];

// Install event
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(urlsToCache);
    }),
  );
  // Activate this worker immediately; don't wait for old one to finish
  self.skipWaiting();
});

function rememberPage(event, url, response) {
  if (url.pathname.startsWith("/accounts/")) {
    event.waitUntil(caches.delete(PAGES_CACHE));
    return;
  }
  const isHtml = (response.headers.get("Content-Type") || "").includes("text/html");
  if (url.pathname !== HOME_PATH || url.search || !response.ok || response.type !== "basic" || !isHtml) {
    return;
  }
  const copy = response.clone();
  event.waitUntil(caches.open(PAGES_CACHE).then((cache) => cache.put(HOME_PATH, copy)));
}

async function offlinePage() {
  const headers = { "Content-Type": "text/html; charset=utf-8" };
  const cached = await caches.match(HOME_PATH, { cacheName: PAGES_CACHE });
  if (!cached) {
    return new Response(
      '<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">'
        + "<title>Offline · Floppy</title>"
        + '<body style="margin:0;display:grid;place-items:center;min-height:100vh;background:#16171d;color:#e7e8ee;font-family:system-ui,sans-serif">'
        + "<p>You're offline. Floppy will load again once you're connected.</p></body>",
      { status: 503, headers },
    );
  }
  const savedAt = cached.headers.get("Date");
  const when = savedAt ? ` from ${new Date(savedAt).toLocaleString()}` : "";
  const banner = '<div role="status" data-floppy-offline style="position:fixed;z-index:2147483647;left:50%;'
    + "bottom:calc(env(safe-area-inset-bottom) + 104px);transform:translateX(-50%);max-width:calc(100vw - 32px);"
    + "padding:8px 14px;border-radius:999px;background:#2b2d36;color:#f2f3f7;font:500 13px/1.3 system-ui,sans-serif;"
    + `box-shadow:0 6px 20px rgb(0 0 0 / 40%);pointer-events:none">You're offline. This is your Home${when}.</div>`;
  const html = (await cached.text()).replace(/<body([^>]*)>/i, `<body$1>${banner}`);
  return new Response(html, { headers });
}

async function handleNavigation(event, url) {
  try {
    // The preloaded response when there is one, so the request is made once.
    const response = (await event.preloadResponse) || (await fetch(event.request));
    rememberPage(event, url, response);
    return response;
  } catch (error) {
    return offlinePage();
  }
}

// Fetch event
self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Only cache same-origin static assets.
  const isSameOrigin = url.origin === self.location.origin;
  const isHtmxRequest = request.headers.get("HX-Request") === "true";

  // A6: page loads go to the network (preloaded) and fall back to the last
  // Home only when the network is not available.
  if (
    request.mode === "navigate" &&
    request.method === "GET" &&
    isSameOrigin &&
    !PASS_THROUGH_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))
  ) {
    event.respondWith(handleNavigation(event, url));
    return;
  }

  // The JavaScript i18n catalog is not under /static/, but every page needs
  // it: network first, with the stored copy for the offline Home.
  if (request.method === "GET" && isSameOrigin && url.pathname === "/jsi18n/") {
    event.respondWith(
      fetch(request)
        .then((networkResponse) => {
          if (networkResponse.ok) {
            const responseClone = networkResponse.clone();
            event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone)));
          }
          return networkResponse;
        })
        .catch(() => caches.match(request).then((cached) => cached || Response.error())),
    );
    return;
  }

  // Keep the other app requests (fragments, HTMX, POSTs) on the network to
  // avoid stale dynamic HTML.
  //
  // Return before respondWith. The browser then makes the request on its own
  // network path. Calling respondWith(fetch(request)) here made the worker
  // repeat a request that the browser can do without help. It also replaced
  // the browser offline page with a failed promise, and it stopped navigation
  // preload.
  if (
    request.method !== "GET" ||
    !isSameOrigin ||
    isHtmxRequest ||
    !url.pathname.startsWith("/static/")
  ) {
    return;
  }

  // Cache-first for static assets only.
  event.respondWith(
    caches.match(request).then((response) => {
      if (response) {
        return response;
      }

      return fetch(request)
        .then((networkResponse) => {
          if (networkResponse.ok) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
          }
          return networkResponse;
        })
        .catch(async (error) => {
          // The network is not available. Static URLs contain a file
          // modification time (main.css?1786502224). An exact match fails
          // after each rebuild, because the time changes. Give the previous
          // version instead. A previous version is better than a page that
          // cannot load.
          const previousVersion = await caches.match(request, {
            ignoreSearch: true,
          });
          if (previousVersion) {
            return previousVersion;
          }
          throw error;
        });
    }),
  );
});

// Activate event
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((cacheNames) =>
        Promise.all(
          cacheNames.map((cacheName) => {
            if (cacheName !== CACHE_NAME && cacheName !== PAGES_CACHE) {
              return caches.delete(cacheName);
            }

            return undefined;
          }),
        ),
      )
      .then(() => self.registration.navigationPreload && self.registration.navigationPreload.enable())
      .then(() => self.clients.claim()),
  );
});
