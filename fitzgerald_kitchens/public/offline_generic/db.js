// IndexedDB wrapper for the unified Offline Sync PWA (DocTypes + My Tasks).
(function (global) {
	"use strict";

	const DB_NAME = "offline_sync_v1";
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

				if (!db.objectStoreNames.contains("config")) {
					db.createObjectStore("config", { keyPath: "key" });
				}

				if (!db.objectStoreNames.contains("docs")) {
					const docs = db.createObjectStore("docs", { keyPath: "id" });
					docs.createIndex("doctype", "doctype");
				}

				if (!db.objectStoreNames.contains("tasks_cache")) {
					db.createObjectStore("tasks_cache", { keyPath: "name" });
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

	function getAllByIndex(storeName, indexName, value) {
		return openDB().then(function (db) {
			return new Promise(function (resolve, reject) {
				const tx = db.transaction(storeName, "readonly");
				const index = tx.objectStore(storeName).index(indexName);
				const request = index.getAll(value);
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

	function clearStore(storeName) {
		return withStore(storeName, "readwrite", function (store) {
			store.clear();
		});
	}

	function docId(doctype, name) {
		return doctype + "::" + name;
	}

	global.osOfflineDB = {
		openDB: openDB,
		put: put,
		get: get,
		getAll: getAll,
		getAllByIndex: getAllByIndex,
		remove: remove,
		clearStore: clearStore,
		docId: docId,
	};
})(window);
