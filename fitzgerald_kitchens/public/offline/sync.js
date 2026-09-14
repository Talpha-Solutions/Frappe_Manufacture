// Outbox sync engine for the Fitzgerald Kitchens offline field app.
// Drains the IndexedDB `outbox` store to offline_engine.api.push whenever the
// device is online, with per-item retry/backoff. Depends on db.js.
(function (global) {
	"use strict";

	const db = global.fkOfflineDB;
	const PUSH_URL = "/api/method/fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.api.push";
	const STATUS_URL = "/api/method/fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.api.status";
	const PULL_URL = "/api/method/fitzgerald_kitchens.fitzgerald_kitchens.offline.pull.pull";
	const UPLOAD_URL = "/api/method/upload_file";
	const BATCH_SIZE = 20;
	const POLL_INTERVAL_MS = 30000;
	const MAX_BACKOFF_MS = 5 * 60 * 1000;

	// crypto.randomUUID is only exposed in secure contexts (https, or
	// localhost/127.0.0.1/*.localhost); fall back to a plain UUID v4 elsewhere.
	function genUuid() {
		if (global.crypto && typeof global.crypto.randomUUID === "function") {
			return global.crypto.randomUUID();
		}
		return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
			const r = (Math.random() * 16) | 0;
			const v = c === "x" ? r : (r & 0x3) | 0x8;
			return v.toString(16);
		});
	}

	let syncing = false;
	let authRequired = false;
	let lastSyncError = null;
	const listeners = [];

	function getLastSyncError() {
		return lastSyncError;
	}

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
		// frappe.csrf_token is the live value Frappe's own frappe.call() uses and
		// keeps refreshed (see desk.js's cross-tab boot broadcast). The static
		// <meta name="csrf-token"> tag is only ever set once at initial page
		// render and goes stale after any session/cache event that rotates the
		// token — using it caused every push to fail with CSRFTokenError until
		// the page was hard-reloaded.
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
				id = window.localStorage.getItem("fk_device_id");
			} catch (e) {
				/* ignore */
			}
			if (!id) {
				id = genUuid();
			}
			try {
				window.localStorage.setItem("fk_device_id", id);
			} catch (e) {
				/* ignore */
			}
			return db.put("sync_meta", { key: "device_id", value: id }).then(function () {
				return id;
			});
		});
	}

	function queueOperation(operation, payload, doctypeContext) {
		const clientUuid = genUuid();
		const row = {
			client_uuid: clientUuid,
			operation: operation,
			payload: payload,
			doctype_context: doctypeContext || {},
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

	function syncNow() {
		if (syncing || !navigator.onLine || authRequired) {
			return Promise.resolve();
		}

		// Peek at the outbox before flipping the `syncing` flag: if there is
		// nothing to push, skip the notify() cycle entirely. Toggling
		// syncing true->false here even with an empty outbox previously fired
		// a spurious onChange transition that some listeners (e.g. My Tasks'
		// "sync just finished, refresh" handler) treated as real sync
		// activity, causing them to immediately call syncOutbox() again in a
		// tight infinite loop.
		return db.getAll("outbox").then(function (peekRows) {
			const hasPending = peekRows.some(function (r) {
				return r.status === "pending" && backoffDue(r);
			});
			if (!hasPending) {
				return null;
			}
			return syncPending();
		});
	}

	function syncPending() {
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
						return {
							client_uuid: r.client_uuid,
							operation: r.operation,
							payload: r.payload,
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
								return resp
									.text()
									.catch(function () {
										return "";
									})
									.then(function (bodyText) {
										let detail = "";
										try {
											const parsed = JSON.parse(bodyText);
											detail = parsed.exc_type || parsed.exception || "";
										} catch (e) {
											/* not JSON */
										}
										throw new Error(
											"push failed with status " + resp.status + (detail ? ": " + detail : "")
										);
									});
							}
							lastSyncError = null;
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
										return db.remove("outbox", row.client_uuid);
									}
									if (result.status === "Rejected") {
										const isConflict = !!(
											result.server_result && result.server_result.conflict
										);
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
								// Leave outbox rows as pending — do not burn attempts as failed.
								return null;
							}
							console.warn("Sync push failed (will retry):", err);
							lastSyncError = { message: String(err && err.message ? err.message : err), at: Date.now() };
							notify();
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
			syncNow().then(pullNow);
		}
	}

	function fetchStatus() {
		return getDeviceId().then(function (deviceId) {
			return fetch(STATUS_URL + "?device_id=" + encodeURIComponent(deviceId), {
				credentials: "same-origin",
				headers: { "X-Frappe-CSRF-Token": csrfToken() },
			})
				.then(handleAuthResponse)
				.then(function (resp) {
					return resp.ok ? resp.json() : null;
				})
				.then(function (data) {
					if (data) {
						return clearAuthRequired().then(function () {
							return data.message;
						});
					}
					return null;
				})
				.catch(function (err) {
					if (err && err.authRequired) {
						return null;
					}
					return null;
				});
		});
	}

	function pullNow() {
		if (!navigator.onLine || authRequired) {
			return Promise.resolve(null);
		}

		return Promise.all([getDeviceId(), db.get("sync_meta", "cursor")]).then(function (results) {
			const deviceId = results[0];
			const cursorRow = results[1];
			const cursor = cursorRow ? cursorRow.value : null;

			const params = new URLSearchParams({ device_id: deviceId });
			if (cursor) {
				params.set("cursor", cursor);
			}

			return fetch(PULL_URL + "?" + params.toString(), {
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
						writes.push(db.put("tasks_cache", Object.assign({ _bucket: "today" }, task)));
					});
					(message.development_units || []).forEach(function (du) {
						writes.push(db.put("development_units", du));
					});

					return Promise.all(writes).then(function () {
						if (!message.has_more) {
							return db.put("sync_meta", { key: "cursor", value: message.next_cursor });
						}
						return pullNow();
					});
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
		});
	}

	// `attachTo` is optional {doctype, docname} — when given, Frappe's
	// upload_file endpoint links the uploaded file to that document directly.
	// Kept as a trailing param (rather than replacing `developmentUnit`) so
	// existing Development Unit evidence callers don't need to change.
	function uploadEvidenceFile(clientUuid, filename, blob, developmentUnit, attachTo) {
		const formData = new FormData();
		formData.append("file", blob, clientUuid + "_" + filename);
		formData.append("is_private", "1");
		if (developmentUnit) {
			formData.append("doctype", "Development Unit");
			formData.append("docname", developmentUnit);
		} else if (attachTo && attachTo.doctype && attachTo.docname) {
			formData.append("doctype", attachTo.doctype);
			formData.append("docname", attachTo.docname);
		}

		return fetch(UPLOAD_URL, {
			method: "POST",
			credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrfToken() },
			body: formData,
		})
			.then(handleAuthResponse)
			.then(function (resp) {
				if (!resp.ok) {
					throw new Error("upload failed with status " + resp.status);
				}
				return clearAuthRequired().then(function () {
					return resp.json();
				});
			})
			.then(function (data) {
				const message = data && data.message;
				if (!message || !message.file_url) {
					throw new Error("upload response missing file_url");
				}
				return message.file_url;
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
		return Promise.resolve()
			.then(function () {
				return db.remove("outbox", clientUuid);
			})
			.then(function () {
				if (!db.remove) {
					return null;
				}
				return db.remove("evidence", clientUuid).catch(function () {
					return null;
				});
			})
			.then(function () {
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
					return pullNow();
				});
			}

			if (mode === "retry_with_server_state") {
				const payload = Object.assign({}, row.payload || {});
				const serverModified =
					row.conflict_state && row.conflict_state.modified
						? row.conflict_state.modified
						: null;
				if (!serverModified || payload.based_on_modified === undefined) {
					// Cannot safely rewrite CAS — fall back to discard + pull
					return discardOperation(clientUuid).then(function () {
						return pullNow();
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
					return syncNow().then(pullNow);
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

	global.fkOfflineSync = {
		queueOperation: queueOperation,
		syncNow: syncNow,
		pullNow: pullNow,
		uploadEvidenceFile: uploadEvidenceFile,
		genUuid: genUuid,
		fetchStatus: fetchStatus,
		getDeviceId: getDeviceId,
		isSyncing: function () {
			return syncing;
		},
		isAuthRequired: isAuthRequired,
		clearAuthRequired: clearAuthRequired,
		getLastSyncError: getLastSyncError,
		retryOperation: retryOperation,
		discardOperation: discardOperation,
		retryAllFailed: retryAllFailed,
		resolveConflict: resolveConflict,
		onChange: onChange,
	};
})(window);
