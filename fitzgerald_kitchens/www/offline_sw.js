// Service worker for Fitzgerald offline.
// My Tasks Desk URLs: cache real Desk responses; offline fallback = My Tasks shell
// (never the old /offline_app field HTML at Desk URLs).
// /desk/task is the Task DocType — NOT My Tasks — and is not made offline.

const CACHE_PREFIX = "fk-offline-shell-";
const CACHE_NAME = CACHE_PREFIX + "v13";

const FIELD_SHELL_URLS = [
	"/offline_app",
	"/offline_manifest.json",
	"/assets/fitzgerald_kitchens/offline/db.js",
	"/assets/fitzgerald_kitchens/offline/sync.js",
	"/assets/fitzgerald_kitchens/offline/app.js",
];

const MY_TASKS_SHELL = "/my_tasks_desk_offline";

const DESK_PRECACHE_URLS = [
	"/app/my-tasks",
	"/desk/my-tasks",
	MY_TASKS_SHELL,
	"/assets/fitzgerald_kitchens/offline/db.js",
	"/assets/fitzgerald_kitchens/offline/sync.js",
	"/assets/fitzgerald_kitchens/js/my_tasks_offline.js",
	"/assets/fitzgerald_kitchens/js/task_camera.js",
];

function cacheUrls(cache, urls) {
	// cache.add(url) fetches with the default HTTP cache mode, which happily
	// reuses a still-fresh browser HTTP cache entry (our /assets/*.js files
	// serve Cache-Control: max-age=43200) instead of hitting the network —
	// so bumping CACHE_NAME alone can silently re-precache stale bytes.
	// Force a real network round-trip here so precache always reflects what
	// the server is actually serving right now.
	return Promise.all(
		urls.map(function (url) {
			return fetch(url, { cache: "reload" })
				.then(function (response) {
					return cache.put(url, response);
				})
				.catch(function (err) {
					console.warn("SW cache miss:", url, err);
				});
		})
	);
}

function isMyTasksDeskPath(pathname) {
	return (
		pathname === "/app/my-tasks" ||
		pathname === "/desk/my-tasks" ||
		pathname.indexOf("/app/my-tasks") === 0 ||
		pathname.indexOf("/desk/my-tasks") === 0
	);
}

function isTaskDoctypePath(pathname) {
	// ERPNext Task DocType list/form — NOT the My Tasks page.
	return (
		pathname === "/desk/task" ||
		pathname === "/app/task" ||
		pathname.indexOf("/desk/task/") === 0 ||
		pathname.indexOf("/app/task/") === 0 ||
		pathname === "/app/List/Task" ||
		pathname.indexOf("/app/List/Task") === 0
	);
}

function isOfflineAppPath(pathname) {
	return pathname === "/offline_app" || pathname.indexOf("/offline_app") === 0;
}

function helpfulWrongPageResponse() {
	var html =
		"<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\">" +
		"<title>Offline — wrong page</title><style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:2rem auto;padding:1rem;line-height:1.5}" +
		"code{background:#f1f5f9;padding:0.1rem 0.35rem;border-radius:4px}a{color:#1b66ec}</style></head><body>" +
		"<h1>This is not My Tasks</h1>" +
		"<p>You opened the <strong>Task</strong> DocType (<code>/desk/task</code>). That page is online-only.</p>" +
		"<p>Offline My Tasks is here:</p>" +
		"<p><a href=\"/app/my-tasks\">/app/my-tasks</a> &nbsp;·&nbsp; <a href=\"/my_tasks_desk_offline\">/my_tasks_desk_offline</a></p>" +
		"<p>Also use <code>http://127.0.0.1:8001</code> (not <code>manufacture.local</code>) so the Service Worker can install.</p>" +
		"</body></html>";
	return new Response(html, {
		status: 200,
		headers: { "Content-Type": "text/html; charset=utf-8" },
	});
}

function cachedMyTasksOffline() {
	return caches.match("/app/my-tasks").then(function (desk) {
		if (desk) {
			return desk;
		}
		return caches.match("/desk/my-tasks").then(function (desk2) {
			if (desk2) {
				return desk2;
			}
			return caches.match(MY_TASKS_SHELL).then(function (shell) {
				return shell || Response.error();
			});
		});
	});
}

function cachedFieldShell() {
	return caches.match("/offline_app").then(function (page) {
		return page || Response.error();
	});
}

self.addEventListener("install", function (event) {
	event.waitUntil(
		caches
			.open(CACHE_NAME)
			.then(function (cache) {
				return cacheUrls(cache, FIELD_SHELL_URLS.concat(DESK_PRECACHE_URLS));
			})
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

	const path = url.pathname;

	// Wrong page: Task DocType — explain instead of Chrome dinosaur when SW is active.
	if (event.request.mode === "navigate" && isTaskDoctypePath(path)) {
		event.respondWith(
			fetch(event.request).catch(function () {
				return helpfulWrongPageResponse();
			})
		);
		return;
	}

	if (event.request.mode === "navigate" && isMyTasksDeskPath(path)) {
		event.respondWith(
			fetch(event.request)
				.then(function (response) {
					if (response && response.ok) {
						const clone = response.clone();
						caches.open(CACHE_NAME).then(function (cache) {
							cache.put("/app/my-tasks", clone.clone());
							cache.put(path, clone);
						});
					}
					return response;
				})
				.catch(function () {
					return cachedMyTasksOffline();
				})
		);
		return;
	}

	if (event.request.mode === "navigate" && (path === MY_TASKS_SHELL || path.indexOf(MY_TASKS_SHELL) === 0)) {
		event.respondWith(
			fetch(event.request)
				.then(function (response) {
					if (response && response.ok) {
						const clone = response.clone();
						caches.open(CACHE_NAME).then(function (cache) {
							cache.put(MY_TASKS_SHELL, clone);
						});
					}
					return response;
				})
				.catch(function () {
					return caches.match(MY_TASKS_SHELL).then(function (p) {
						return p || Response.error();
					});
				})
		);
		return;
	}

	if (event.request.mode === "navigate" && isOfflineAppPath(path)) {
		event.respondWith(
			fetch(event.request)
				.then(function (response) {
					if (response && response.ok) {
						const clone = response.clone();
						caches.open(CACHE_NAME).then(function (cache) {
							cache.put("/offline_app", clone);
						});
					}
					return response;
				})
				.catch(function () {
					return cachedFieldShell();
				})
		);
		return;
	}

	// Network-first for everything else (mainly our own JS/CSS): while online,
	// always serve the current file so code changes actually take effect —
	// cache-first here meant a stale JS file, once cached, was served forever
	// with no way to pick up updates short of bumping CACHE_NAME. Cache is
	// still updated on every successful fetch, and used only as the offline
	// fallback when the network request fails.
	//
	// A plain fetch(event.request) still honors the *browser's own* HTTP
	// cache — our /assets/*.js responses serve Cache-Control: max-age=43200
	// — so "network-first" could silently resolve from a stale 12h-old disk
	// cache entry without ever reaching the server. Force real revalidation
	// for our own same-origin GETs so this actually behaves network-first.
	const networkRequest =
		url.origin === self.location.origin && event.request.method === "GET"
			? new Request(event.request, { cache: "no-cache" })
			: event.request;

	event.respondWith(
		fetch(networkRequest)
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
					if (event.request.mode === "navigate" && isMyTasksDeskPath(path)) {
						return cachedMyTasksOffline();
					}
					if (event.request.mode === "navigate" && isTaskDoctypePath(path)) {
						return helpfulWrongPageResponse();
					}
					if (event.request.mode === "navigate" && isOfflineAppPath(path)) {
						return cachedFieldShell();
					}
					return Response.error();
				});
			})
	);
});
