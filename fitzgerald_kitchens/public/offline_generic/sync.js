// Outbox + pull engine for the generic Offline Sync PWA.
(function (global) {
	"use strict";

	const db = global.osOfflineDB;
	const PUSH_URL = "/api/method/fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.api.push";
	const STATUS_URL = "/api/method/fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.api.status";
	const PULL_URL = "/api/method/fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.generic_pull.pull";
	const CONFIG_URL = "/api/method/fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.generic_pull.get_offline_config";
	const FK_PULL_URL = "/api/method/fitzgerald_kitchens.fitzgerald_kitchens.offline.pull.pull";
	const MY_TASKS_DASHBOARD_URL =
		"/api/method/fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.my_tasks.get_my_tasks_dashboard";
	const BATCH_SIZE = 20;
	const POLL_INTERVAL_MS = 30000;
	const MAX_BACKOFF_MS = 5 * 60 * 1000;

	let syncing = false;
	let authRequired = false;
	const listeners = [];

	function onChange(fn) {
		listeners.push(fn);
	}

	function notify() {
		listeners.forEach(function (fn) {
			try {
				fn();
			} catch (e) {
				console.error(e);
			}
		});
	}

	function csrfToken() {
		// See public/offline/sync.js for why: frappe.csrf_token is the live,
		// kept-fresh value; the static meta tag goes stale after cache/session
		// events and causes every push to fail with CSRFTokenError.
		if (window.frappe && frappe.csrf_token) {
			return frappe.csrf_token;
		}
		const meta = document.querySelector('meta[name="csrf-token"]');
		return meta ? meta.getAttribute("content") : "";
	}

	function setAuthRequired(value) {
		authRequired = !!value;
		return db.put("sync_meta", { key: "auth_required", value: authRequired }).then(function () {
			notify();
			return authRequired;
		});
	}

	function loadAuthRequired() {
		return db.get("sync_meta", "auth_required").then(function (row) {
			authRequired = !!(row && row.value);
			return authRequired;
		});
	}

	function clearAuthRequired() {
		return setAuthRequired(false);
	}

	function isAuthRequired() {
		return authRequired;
	}

	function handleAuthResponse(resp) {
		if (resp && (resp.status === 401 || resp.status === 403)) {
			return setAuthRequired(true).then(function () {
				const err = new Error("auth_required");
				err.authRequired = true;
				err.status = resp.status;
				throw err;
			});
		}
		return Promise.resolve(resp);
	}

	function getDeviceId() {
		return db.get("sync_meta", "device_id").then(function (row) {
			if (row && row.value) {
				return row.value;
			}
			let id = null;
			try {
				id = window.localStorage.getItem("os_device_id");
			} catch (e) {
				/* ignore */
			}
			if (!id) {
				id = crypto.randomUUID();
			}
			try {
				window.localStorage.setItem("os_device_id", id);
			} catch (e) {
				/* ignore */
			}
			return db.put("sync_meta", { key: "device_id", value: id }).then(function () {
				return id;
			});
		});
	}

	function queueOperation(operation, payload) {
		const clientUuid = crypto.randomUUID();
		const row = {
			client_uuid: clientUuid,
			operation: operation,
			payload: payload,
			status: "pending",
			created_at: Date.now(),
			last_attempt_at: null,
			attempt_count: 0,
			error: null,
		};
		return db.put("outbox", row).then(function () {
			notify();
			maybeSyncNow();
			return row;
		});
	}

	function backoffDue(row) {
		if (!row.last_attempt_at) {
			return true;
		}
		const wait = Math.min(Math.pow(2, row.attempt_count || 0) * 5000, MAX_BACKOFF_MS);
		return Date.now() - row.last_attempt_at >= wait;
	}

	function applyServerDoc(result) {
		if (!result || !result.doctype || !result.name) {
			return Promise.resolve();
		}
		const doc = result.doc || {
			doctype: result.doctype,
			name: result.name,
			modified: result.modified,
		};
		const title = doc._title || doc.name;
		return db.put("docs", {
			id: db.docId(result.doctype, result.name),
			doctype: result.doctype,
			name: result.name,
			title: title,
			modified: result.modified || doc.modified,
			doc: doc,
		});
	}

	function syncNow() {
		if (syncing || !navigator.onLine || authRequired) {
			return Promise.resolve();
		}

		syncing = true;
		notify();

		return db
			.getAll("outbox")
			.then(function (rows) {
				const pending = rows
					.filter(function (r) {
						return r.status === "pending" && backoffDue(r);
					})
					.sort(function (a, b) {
						return a.created_at - b.created_at;
					})
					.slice(0, BATCH_SIZE);

				if (!pending.length) {
					return null;
				}

				return getDeviceId().then(function (deviceId) {
					const operations = pending.map(function (r) {
						const payload = Object.assign({}, r.payload || {});
						delete payload._local_id;
						return {
							client_uuid: r.client_uuid,
							operation: r.operation,
							payload: payload,
							device_id: deviceId,
						};
					});

					return fetch(PUSH_URL, {
						method: "POST",
						credentials: "same-origin",
						headers: {
							"Content-Type": "application/json",
							"X-Frappe-CSRF-Token": csrfToken(),
						},
						body: JSON.stringify({ operations: operations }),
					})
						.then(handleAuthResponse)
						.then(function (resp) {
							if (!resp.ok) {
								throw new Error("push failed with status " + resp.status);
							}
							return clearAuthRequired().then(function () {
								return resp.json();
							});
						})
						.then(function (data) {
							const results = (data && data.message) || [];
							const byUuid = {};
							results.forEach(function (r) {
								byUuid[r.client_uuid] = r;
							});

							return Promise.all(
								pending.map(function (row) {
									const result = byUuid[row.client_uuid];
									if (!result) {
										row.status = "pending";
										row.last_attempt_at = Date.now();
										row.attempt_count = (row.attempt_count || 0) + 1;
										return db.put("outbox", row);
									}
									if (result.status === "Success") {
										return applyServerDoc(result.server_result)
											.then(function () {
												return applyTaskOpSuccess(row);
											})
											.then(function () {
												if (row.operation === "doc.insert" && row.payload && row.payload._local_id) {
													return db.remove("docs", row.payload._local_id).then(function () {
														return db.remove("outbox", row.client_uuid);
													});
												}
												return db.remove("outbox", row.client_uuid);
											});
									}
									if (result.status === "Rejected") {
										const isConflict = !!(result.server_result && result.server_result.conflict);
										row.status = isConflict ? "conflict" : "failed";
										row.error = result.error || "Rejected by server";
										row.conflict_state =
											(result.server_result && result.server_result.current_state) || null;
										row.last_attempt_at = Date.now();
										return db.put("outbox", row);
									}
									if (result.status === "Failed") {
										row.status = "failed";
										row.error = result.error || "Failed on server";
										row.last_attempt_at = Date.now();
										return db.put("outbox", row);
									}
									row.status = "pending";
									row.last_attempt_at = Date.now();
									row.attempt_count = (row.attempt_count || 0) + 1;
									return db.put("outbox", row);
								})
							);
						})
						.catch(function (err) {
							if (err && err.authRequired) {
								return null;
							}
							console.warn("Sync push failed (will retry):", err);
							return Promise.all(
								pending.map(function (row) {
									row.last_attempt_at = Date.now();
									row.attempt_count = (row.attempt_count || 0) + 1;
									return db.put("outbox", row);
								})
							);
						});
				});
			})
			.finally(function () {
				syncing = false;
				notify();
			});
	}

	function maybeSyncNow() {
		if (navigator.onLine && !authRequired) {
			syncNow().then(function () {
				return pullNow();
			});
		}
	}

	function fetchConfig() {
		if (!navigator.onLine) {
			return db.get("config", "offline_config").then(function (row) {
				return row ? row.value : null;
			});
		}
		if (authRequired) {
			return db.get("config", "offline_config").then(function (row) {
				return row ? row.value : null;
			});
		}

		return fetch(CONFIG_URL, {
			credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrfToken() },
		})
			.then(handleAuthResponse)
			.then(function (resp) {
				return resp.ok ? resp.json() : null;
			})
			.then(function (data) {
				const message = data && data.message;
				if (!message) {
					return null;
				}
				return clearAuthRequired().then(function () {
					return db.put("config", { key: "offline_config", value: message }).then(function () {
						return message;
					});
				});
			})
			.catch(function (err) {
				if (err && err.authRequired) {
					return db.get("config", "offline_config").then(function (row) {
						return row ? row.value : null;
					});
				}
				console.warn("Config fetch failed:", err);
				return db.get("config", "offline_config").then(function (row) {
					return row ? row.value : null;
				});
			});
	}

	function applyTaskOpSuccess(row) {
		if (!row || !row.operation) {
			return Promise.resolve();
		}
		if (row.operation === "task.complete_task" && row.payload && row.payload.task) {
			const name = row.payload.task;
			return db.get("tasks_cache", name).then(function (task) {
				if (!task) {
					return null;
				}
				task.status = "Completed";
				task._bucket = "completed";
				task._pending_complete = false;
				return db.put("tasks_cache", task);
			});
		}
		return Promise.resolve();
	}

	function getCachedConfig() {
		return db.get("config", "offline_config").then(function (row) {
			return row ? row.value : null;
		});
	}

	function pullGeneric(fullRefresh) {
		return Promise.all([getDeviceId(), db.get("sync_meta", "since")]).then(function (results) {
			const sinceRow = results[1];
			const since = !fullRefresh && sinceRow ? sinceRow.value : null;
			const params = new URLSearchParams();
			if (since) {
				params.set("since", since);
			}

			return fetch(PULL_URL + (params.toString() ? "?" + params.toString() : ""), {
				credentials: "same-origin",
				headers: { "X-Frappe-CSRF-Token": csrfToken() },
			})
				.then(handleAuthResponse)
				.then(function (resp) {
					if (!resp.ok) {
						return null;
					}
					return clearAuthRequired().then(function () {
						return resp.json();
					});
				})
				.then(function (data) {
					const message = data && data.message;
					if (!message || !message.enabled) {
						return null;
					}

					const writes = [];
					const docsMap = message.docs || {};
					Object.keys(docsMap).forEach(function (doctype) {
						(docsMap[doctype] || []).forEach(function (doc) {
							writes.push(
								db.put("docs", {
									id: db.docId(doctype, doc.name),
									doctype: doctype,
									name: doc.name,
									title: doc._title || doc.name,
									modified: doc.modified,
									doc: doc,
								})
							);
						});
					});

					return Promise.all(writes).then(function () {
						if (message.server_time) {
							return db.put("sync_meta", { key: "since", value: message.server_time });
						}
					});
				});
		});
	}

	function refreshMyTasksDashboard() {
		return fetch(MY_TASKS_DASHBOARD_URL, {
			credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrfToken() },
		})
			.then(handleAuthResponse)
			.then(function (resp) {
				return resp.ok
					? clearAuthRequired().then(function () {
							return resp.json();
					  })
					: null;
			})
			.then(function (data) {
				const message = data && data.message;
				if (!message || !message.tabs) {
					return null;
				}
				const writes = [];
				Object.keys(message.tabs).forEach(function (bucket) {
					(message.tabs[bucket].tasks || []).forEach(function (task) {
						writes.push(db.put("tasks_cache", Object.assign({}, task, { _bucket: bucket })));
					});
				});
				return Promise.all(writes);
			});
	}

	function pullMyTasksIncremental() {
		return Promise.all([getDeviceId(), db.get("sync_meta", "fk_cursor")]).then(function (results) {
			const deviceId = results[0];
			const cursorRow = results[1];
			const cursor = cursorRow ? cursorRow.value : null;
			const params = new URLSearchParams({ device_id: deviceId });
			if (cursor) {
				params.set("cursor", cursor);
			}

			return fetch(FK_PULL_URL + "?" + params.toString(), {
				credentials: "same-origin",
				headers: { "X-Frappe-CSRF-Token": csrfToken() },
			})
				.then(handleAuthResponse)
				.then(function (resp) {
					if (!resp.ok) {
						return null;
					}
					return clearAuthRequired().then(function () {
						return resp.json();
					});
				})
				.then(function (data) {
					const message = data && data.message;
					if (!message) {
						return null;
					}

					const writes = [];
					(message.tasks || []).forEach(function (task) {
						writes.push(
							db.put(
								"tasks_cache",
								Object.assign({ _bucket: "today" }, task, {
									subject: task.subject || task.name,
								})
							)
						);
					});

					return Promise.all(writes).then(function () {
						if (!message.has_more) {
							if (message.next_cursor) {
								return db.put("sync_meta", { key: "fk_cursor", value: message.next_cursor });
							}
							return null;
						}
						return pullMyTasksIncremental();
					});
				});
		});
	}

	function pullMyTasks(fullRefresh) {
		const start = fullRefresh
			? db.put("sync_meta", { key: "fk_cursor", value: null }).then(refreshMyTasksDashboard)
			: refreshMyTasksDashboard();
		return start
			.then(function () {
				return pullMyTasksIncremental();
			})
			.catch(function (err) {
				if (err && err.authRequired) {
					return null;
				}
				console.warn("My Tasks pull failed:", err);
				return null;
			});
	}

	function pullNow(fullRefresh) {
		if (!navigator.onLine || authRequired) {
			return Promise.resolve(null);
		}

		return getCachedConfig()
			.then(function (cfg) {
				const jobs = [];
				if (!cfg || cfg.generic_enabled || (cfg.doctypes && cfg.doctypes.length)) {
					jobs.push(
						pullGeneric(fullRefresh).catch(function (err) {
							if (err && err.authRequired) {
								throw err;
							}
							console.warn("Generic pull failed:", err);
							return null;
						})
					);
				}
				// My Tasks is not shown on this page (see app.js) — don't pull its
				// dashboard here either, to avoid a second, disconnected local
				// cache/outbox from drifting alongside the Desk page's own.
				if (!jobs.length) {
					return null;
				}
				return Promise.all(jobs);
			})
			.catch(function (err) {
				if (err && err.authRequired) {
					return null;
				}
				console.warn("Pull failed:", err);
				return null;
			})
			.then(function () {
				notify();
			});
	}

	function fetchStatus() {
		return getDeviceId().then(function (deviceId) {
			return fetch(STATUS_URL + "?device_id=" + encodeURIComponent(deviceId) + "&app_name=fitzgerald_kitchens", {
				credentials: "same-origin",
				headers: { "X-Frappe-CSRF-Token": csrfToken() },
			})
				.then(handleAuthResponse)
				.then(function (resp) {
					return resp.ok ? resp.json() : null;
				})
				.then(function (data) {
					return data ? data.message : null;
				})
				.catch(function () {
					return null;
				});
		});
	}

	function retryOperation(clientUuid) {
		return db.get("outbox", clientUuid).then(function (row) {
			if (!row) {
				return null;
			}
			row.status = "pending";
			row.error = null;
			row.conflict_state = null;
			row.attempt_count = 0;
			row.last_attempt_at = null;
			return db.put("outbox", row).then(function () {
				notify();
				return syncNow();
			});
		});
	}

	function discardOperation(clientUuid) {
		return db.remove("outbox", clientUuid).then(function () {
			notify();
		});
	}

	function retryAllFailed() {
		return db.getAll("outbox").then(function (rows) {
			const failed = rows.filter(function (r) {
				return r.status === "failed";
			});
			return Promise.all(
				failed.map(function (row) {
					row.status = "pending";
					row.error = null;
					row.conflict_state = null;
					row.attempt_count = 0;
					row.last_attempt_at = null;
					return db.put("outbox", row);
				})
			).then(function () {
				notify();
				return syncNow();
			});
		});
	}

	function resolveConflict(clientUuid, mode) {
		return db.get("outbox", clientUuid).then(function (row) {
			if (!row || row.status !== "conflict") {
				return null;
			}

			if (mode === "discard") {
				return discardOperation(clientUuid).then(function () {
					return pullNow(true);
				});
			}

			if (mode === "retry_with_server_state") {
				const payload = Object.assign({}, row.payload || {});
				const serverModified =
					row.conflict_state && row.conflict_state.modified
						? row.conflict_state.modified
						: null;
				if (!serverModified || payload.based_on_modified === undefined) {
					return discardOperation(clientUuid).then(function () {
						return pullNow(true);
					});
				}
				payload.based_on_modified = serverModified;
				row.payload = payload;
				row.status = "pending";
				row.error = null;
				row.conflict_state = null;
				row.attempt_count = 0;
				row.last_attempt_at = null;
				return db.put("outbox", row).then(function () {
					notify();
					return syncNow().then(function () {
						return pullNow(true);
					});
				});
			}

			return null;
		});
	}

	window.addEventListener("online", maybeSyncNow);
	document.addEventListener("visibilitychange", function () {
		if (document.visibilityState === "visible") {
			maybeSyncNow();
		}
	});
	setInterval(maybeSyncNow, POLL_INTERVAL_MS);

	loadAuthRequired().then(notify);

	global.osOfflineSync = {
		queueOperation: queueOperation,
		syncNow: syncNow,
		pullNow: pullNow,
		pullMyTasks: pullMyTasks,
		fetchConfig: fetchConfig,
		fetchStatus: fetchStatus,
		getDeviceId: getDeviceId,
		isSyncing: function () {
			return syncing;
		},
		isAuthRequired: isAuthRequired,
		clearAuthRequired: clearAuthRequired,
		retryOperation: retryOperation,
		discardOperation: discardOperation,
		retryAllFailed: retryAllFailed,
		resolveConflict: resolveConflict,
		onChange: onChange,
		maybeSyncNow: maybeSyncNow,
	};
})(window);
