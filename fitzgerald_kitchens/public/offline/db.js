// IndexedDB wrapper for the Fitzgerald Kitchens offline field app.
// Phase 1 stores: `outbox` (queued operations awaiting sync), `sync_meta`
// (device id / small key-value settings), and `tasks_cache` (a read-only
// cache of the My Tasks dashboard, refreshed whenever online).
(function (global) {
	"use strict";

	const DB_NAME = "fk_offline_v1";
	const DB_VERSION = 2;

	let dbPromise = null;

	function openDB() {
		if (dbPromise) {
			return dbPromise;
		}

		dbPromise = new Promise(function (resolve, reject) {
			const request = indexedDB.open(DB_NAME, DB_VERSION);

			request.onupgradeneeded = function (event) {
				const db = event.target.result;

				if (!db.objectStoreNames.contains("outbox")) {
					const outbox = db.createObjectStore("outbox", { keyPath: "client_uuid" });
					outbox.createIndex("status", "status");
					outbox.createIndex("created_at", "created_at");
				}

				if (!db.objectStoreNames.contains("sync_meta")) {
					db.createObjectStore("sync_meta", { keyPath: "key" });
				}

				if (!db.objectStoreNames.contains("tasks_cache")) {
					db.createObjectStore("tasks_cache", { keyPath: "name" });
				}

				if (!db.objectStoreNames.contains("development_units")) {
					const dus = db.createObjectStore("development_units", { keyPath: "name" });
					dus.createIndex("project", "project");
				}

				// Local-only Blob store for evidence photos captured offline,
				// keyed by the same client_uuid used for the outbox row and the
				// eventual `add_evidence` operation, so the two stay linked.
				if (!db.objectStoreNames.contains("evidence")) {
					const evidence = db.createObjectStore("evidence", { keyPath: "client_uuid" });
					evidence.createIndex("upload_status", "upload_status");
				}
			};

			request.onsuccess = function (event) {
				resolve(event.target.result);
			};

			request.onerror = function (event) {
				reject(event.target.error);
			};
		});

		return dbPromise;
	}

	function withStore(storeName, mode, fn) {
		return openDB().then(function (db) {
			return new Promise(function (resolve, reject) {
				const tx = db.transaction(storeName, mode);
				const store = tx.objectStore(storeName);
				const result = fn(store);

				tx.oncomplete = function () {
					resolve(result && result.value !== undefined ? result.value : result);
				};
				tx.onerror = function () {
					reject(tx.error);
				};
			});
		});
	}

	function put(storeName, value) {
		return withStore(storeName, "readwrite", function (store) {
			store.put(value);
			return value;
		});
	}

	function get(storeName, key) {
		return openDB().then(function (db) {
			return new Promise(function (resolve, reject) {
				const tx = db.transaction(storeName, "readonly");
				const request = tx.objectStore(storeName).get(key);
				request.onsuccess = function () {
					resolve(request.result || null);
				};
				request.onerror = function () {
					reject(request.error);
				};
			});
		});
	}

	function getAll(storeName) {
		return openDB().then(function (db) {
			return new Promise(function (resolve, reject) {
				const tx = db.transaction(storeName, "readonly");
				const request = tx.objectStore(storeName).getAll();
				request.onsuccess = function () {
					resolve(request.result || []);
				};
				request.onerror = function () {
					reject(request.error);
				};
			});
		});
	}

	function remove(storeName, key) {
		return withStore(storeName, "readwrite", function (store) {
			store.delete(key);
		});
	}

	global.fkOfflineDB = {
		openDB: openDB,
		put: put,
		get: get,
		getAll: getAll,
		remove: remove,
	};
})(window);
