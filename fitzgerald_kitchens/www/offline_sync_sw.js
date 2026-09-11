// Service worker for the generic Offline Sync PWA.
// Scope is limited to /offline so it never intercepts Frappe Desk.

const CACHE_PREFIX = "offline-sync-shell-";
const CACHE_NAME = CACHE_PREFIX + "v6";

const SHELL_URLS = [
	"/offline",
	"/offline_sync_manifest.json",
	"/assets/fitzgerald_kitchens/offline_generic/app.css",
	"/assets/fitzgerald_kitchens/offline_generic/db.js",
	"/assets/fitzgerald_kitchens/offline_generic/sync.js",
	"/assets/fitzgerald_kitchens/offline_generic/app.js",
];

function cacheShell(cache) {
	return Promise.all(
		SHELL_URLS.map(function (url) {
			return cache.add(url).catch(function (err) {
				console.warn("SW shell cache miss:", url, err);
			});
		})
	);
}

self.addEventListener("install", function (event) {
	event.waitUntil(
		caches
			.open(CACHE_NAME)
			.then(cacheShell)
			.then(function () {
				return self.skipWaiting();
			})
	);
});

self.addEventListener("activate", function (event) {
	event.waitUntil(
		caches
			.keys()
			.then(function (keys) {
				return Promise.all(
					keys
						.filter(function (key) {
							return key.indexOf(CACHE_PREFIX) === 0 && key !== CACHE_NAME;
						})
						.map(function (key) {
							return caches.delete(key);
						})
				);
			})
			.then(function () {
				return self.clients.claim();
			})
	);
});

self.addEventListener("fetch", function (event) {
	const url = new URL(event.request.url);

	if (url.pathname.startsWith("/api/")) {
		return;
	}

	if (event.request.method !== "GET") {
		return;
	}

	// Network-first (see offline_sw.js for why): serve the current file while
	// online so JS/CSS changes actually take effect; cache is only the
	// offline fallback, updated on every successful fetch.
	event.respondWith(
		fetch(event.request)
			.then(function (response) {
				if (response && response.ok && url.origin === self.location.origin) {
					const clone = response.clone();
					caches.open(CACHE_NAME).then(function (cache) {
						cache.put(event.request, clone);
					});
				}
				return response;
			})
			.catch(function () {
				return caches.match(event.request).then(function (cached) {
					if (cached) {
						return cached;
					}
					if (event.request.mode === "navigate") {
						return caches.match("/offline");
					}
					return Response.error();
				});
			})
	);
});
