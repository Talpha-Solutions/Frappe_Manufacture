// Desk My Tasks offline helpers: dashboard cache + outbox via fkOfflineDB / fkOfflineSync.
(function (global) {
	"use strict";

	const DASHBOARD_KEY = "my_tasks_dashboard";

	function db() {
		return global.fkOfflineDB;
	}

	function sync() {
		return global.fkOfflineSync;
	}

	function isOnline() {
		return navigator.onLine;
	}

	/**
	 * Everything currently sitting in the outbox — pending (queued, not yet
	 * pushed), failed/rejected (pushed, server said no — see `error`), and how
	 * many total. Used to show sync issues directly on the My Tasks page,
	 * since this Desk page has no separate "Sync Queue" screen of its own.
	 */
	function getOutboxSummary() {
		const store = db();
		if (!store) {
			return Promise.resolve({ pending: [], problem: [], total: 0 });
		}
		return store.getAll("outbox").then(function (rows) {
			rows = rows || [];
			const pending = rows.filter(function (r) {
				return r.status === "pending";
			});
			const problem = rows.filter(function (r) {
				return r.status === "failed" || r.status === "rejected" || r.status === "conflict";
			});
			return { pending: pending, problem: problem, total: rows.length };
		});
	}

	function saveDashboard(message) {
		const store = db();
		if (!store || !message) {
			return Promise.resolve();
		}
		const writes = [store.put("sync_meta", { key: DASHBOARD_KEY, value: message })];
		const tabs = message.tabs || {};
		Object.keys(tabs).forEach(function (bucket) {
			(tabs[bucket].tasks || []).forEach(function (task) {
				writes.push(store.put("tasks_cache", Object.assign({}, task, { _bucket: bucket })));
			});
		});
		return Promise.all(writes);
	}

	function loadDashboard() {
		const store = db();
		if (!store) {
			return Promise.resolve(null);
		}
		return store.get("sync_meta", DASHBOARD_KEY).then(function (row) {
			if (row && row.value) {
				return row.value;
			}
			return rebuildDashboardFromTasks();
		});
	}

	function rebuildDashboardFromTasks() {
		const store = db();
		return store.getAll("tasks_cache").then(function (tasks) {
			if (!tasks || !tasks.length) {
				return null;
			}
			const tabs = {
				today: { label: "Today", tasks: [] },
				upcoming: { label: "Upcoming", tasks: [] },
				overdue: { label: "Overdue", tasks: [] },
				completed: { label: "Completed", tasks: [] },
			};
			tasks.forEach(function (task) {
				const bucket =
					task._bucket && tabs[task._bucket] ? task._bucket : task.status === "Completed" ? "completed" : "today";
				tabs[bucket].tasks.push(task);
			});
			return {
				user: {
					full_name: (frappe.boot && frappe.boot.user && frappe.boot.user.full_name) || frappe.session.user,
					abbr: "?",
					department: "",
					date_label: frappe.datetime ? frappe.datetime.str_to_user(frappe.datetime.get_today()) : "",
					user_image: "",
				},
				kpis: {
					completed_today: tabs.completed.tasks.length,
					due_today: tabs.today.tasks.length,
					overdue: tabs.overdue.tasks.length,
				},
				projects: [],
				project_filter: "",
				tabs: tabs,
				_from_cache: 1,
			};
		});
	}

	/**
	 * Generic offline-action core: patch a cached task (and its copy inside the
	 * cached dashboard) in place, then queue the same change as an idempotent
	 * outbox operation to replay once online. Any new offline-capable button
	 * should call `queueTaskOperation`, not write its own IndexedDB plumbing.
	 */
	function patchTaskLocally(taskName, patchFn) {
		const store = db();
		if (!store) {
			return Promise.resolve(null);
		}
		return store.get("tasks_cache", taskName).then(function (task) {
			if (!task) {
				return null;
			}
			patchFn(task);
			return store.put("tasks_cache", task).then(function () {
				return task;
			});
		}).then(function (patched) {
			return loadDashboard().then(function (dash) {
				if (!dash || !dash.tabs) {
					return null;
				}
				Object.keys(dash.tabs).forEach(function (bucket) {
					(dash.tabs[bucket].tasks || []).forEach(function (t) {
						if (t.name === taskName) {
							patchFn(t);
						}
					});
				});
				return store.put("sync_meta", { key: DASHBOARD_KEY, value: dash }).then(function () {
					return dash;
				});
			});
		});
	}

	function moveTaskToBucketLocally(taskName, bucket) {
		const store = db();
		if (!store) {
			return Promise.resolve(null);
		}
		return loadDashboard().then(function (dash) {
			if (!dash || !dash.tabs) {
				return null;
			}
			Object.keys(dash.tabs).forEach(function (b) {
				dash.tabs[b].tasks = (dash.tabs[b].tasks || []).filter(function (t) {
					return t.name !== taskName;
				});
			});
			return store.get("tasks_cache", taskName).then(function (task) {
				dash.tabs[bucket] = dash.tabs[bucket] || { label: bucket, tasks: [] };
				dash.tabs[bucket].tasks.unshift(task || { name: taskName });
				dash.kpis = dash.kpis || {};
				dash.kpis.completed_today = (dash.tabs.completed.tasks || []).length;
				return store.put("sync_meta", { key: DASHBOARD_KEY, value: dash }).then(function () {
					return dash;
				});
			});
		});
	}

	/**
	 * Queue any registered offline_sync_operations op (see hooks.py) with an
	 * optimistic local patch applied first. `payload` is sent to the server op
	 * as-is; `patchFn(task)` mutates the cached task (and the cached dashboard's
	 * copy of it) to reflect the change immediately in the UI.
	 */
	function queueTaskOperation(operation, taskName, payload, patchFn) {
		const s = sync();
		if (!s) {
			return Promise.reject(new Error("Offline sync not loaded"));
		}
		return patchTaskLocally(taskName, patchFn || function () {}).then(function (dash) {
			return s.queueOperation(operation, payload, { task: taskName }).then(function () {
				return dash;
			});
		});
	}

	function queueProgress(taskName, progress) {
		return queueTaskOperation(
			"task.update_task_progress",
			taskName,
			{ task: taskName, progress: progress },
			function (task) {
				task.progress = progress;
				task._pending_progress = true;
			}
		);
	}

	function queueComplete(taskName) {
		return queueTaskOperation("task.complete_task", taskName, { task: taskName }, function (task) {
			task.status = "Completed";
			task.progress = 100;
			task.timer_running = false;
			task.timer_paused = false;
			task._bucket = "completed";
			task._pending_complete = true;
		}).then(function () {
			return moveTaskToBucketLocally(taskName, "completed");
		});
	}

	function findLocallyRunningTask(exceptTaskName) {
		const store = db();
		if (!store) {
			return Promise.resolve(null);
		}
		return store.getAll("tasks_cache").then(function (tasks) {
			return (tasks || []).find(function (t) {
				return t.name !== exceptTaskName && t.timer_running;
			}) || null;
		});
	}

	// An unsynced or already-failed task.start_timer/resume_timer op queued
	// for this task, if any — most recent first. Used to detect "started and
	// stopped/paused while offline" so the pair can be merged into one
	// already-closed session instead of the normal two-phase flow — see
	// queueTimerAction and task_timer.py's log_completed_timer_session for
	// why the two-phase flow alone can false-positive on Timesheet's overlap
	// check in that scenario.
	//
	// Deliberately not limited to status === "pending": the device can flip
	// online and sync the bare start (marking it Rejected, since it's the
	// exact same false-positive) *before* the matching stop/pause even gets
	// queued, e.g. via the periodic background sync or a brief connectivity
	// blip — the start doesn't have to still be waiting locally for the
	// pairing to be worth doing, it just has to have never actually
	// succeeded server-side.
	function findUnresolvedStartOp(taskName) {
		const store = db();
		if (!store) {
			return Promise.resolve(null);
		}
		return store.getAll("outbox").then(function (rows) {
			const matches = (rows || [])
				.filter(function (r) {
					return (
						r.status !== "success" &&
						(r.operation === "task.start_timer" || r.operation === "task.resume_timer") &&
						r.doctype_context &&
						r.doctype_context.task === taskName
					);
				})
				.sort(function (a, b) {
					return (b.created_at || 0) - (a.created_at || 0);
				});
			return matches[0] || null;
		});
	}

	function queueTimerAction(method, taskName) {
		const clientTime = frappe.datetime.now_datetime();
		const startLike = method === "start_task_timer" || method === "resume_task_timer";

		const runStart = function () {
			return queueTaskOperation(
				"task." + (method === "resume_task_timer" ? "resume_timer" : "start_timer"),
				taskName,
				{ task: taskName, client_time: clientTime },
				function (task) {
					task.timer_running = true;
					task.timer_paused = false;
					// Seconds, matching the server's timer_started_at_epoch contract
					// (Python's datetime.timestamp()) — NOT milliseconds.
					task.timer_started_at_epoch = Math.floor(Date.now() / 1000);
					task.timer_elapsed_seconds = 0;
					if (task.status === "Open") {
						task.status = "Working";
					}
				}
			);
		};

		if (startLike) {
			return findLocallyRunningTask(taskName).then(function (other) {
				if (!other) {
					return runStart();
				}
				return queueTaskOperation("task.stop_timer", other.name, { task: other.name, client_time: clientTime }, function (task) {
					task.timer_running = false;
					task.timer_paused = false;
				}).then(runStart);
			});
		}

		const paused = method === "pause_task_timer";
		const opName = paused ? "task.pause_timer" : "task.stop_timer";
		const s = sync();

		return findUnresolvedStartOp(taskName).then(function (pendingStart) {
			if (pendingStart && s) {
				const fromClientTime = (pendingStart.payload && pendingStart.payload.client_time) || clientTime;
				return s.discardOperation(pendingStart.client_uuid).then(function () {
					return queueTaskOperation(
						"task.log_completed_session",
						taskName,
						{
							task: taskName,
							from_client_time: fromClientTime,
							to_client_time: clientTime,
							paused: paused,
						},
						function (task) {
							task.timer_running = false;
							task.timer_paused = paused;
						}
					);
				});
			}

			return queueTaskOperation(opName, taskName, { task: taskName, client_time: clientTime }, function (task) {
				task.timer_running = false;
				task.timer_paused = paused;
			});
		});
	}

	function queueDespatch(taskName) {
		const s = sync();
		if (!s) {
			return Promise.reject(new Error("Offline sync not loaded"));
		}
		return s.queueOperation(
			"despatch.submit_despatch_material_request",
			{ task_name: taskName },
			{ task: taskName }
		);
	}

	function syncOutbox() {
		const s = sync();
		if (!s || !isOnline()) {
			return Promise.resolve();
		}
		return Promise.all([s.syncNow(), maybeSyncTaskPhotos()]);
	}

	/**
	 * Task photo capture, offline-capable. Reuses the same two-phase pattern
	 * as Development Unit evidence photos: the blob is stashed in the shared
	 * `evidence` IndexedDB store immediately (works offline), then — once
	 * online — uploaded via the ordinary /api/method/upload_file endpoint and
	 * linked to the Task through a small JSON op pushed through the normal
	 * outbox/offline_engine pipeline (see hooks.py: task.upload_task_photo).
	 */
	function queueTaskPhoto(taskName, blob, filename) {
		const store = db();
		const s = sync();
		if (!store || !s) {
			return Promise.reject(new Error("Offline sync not loaded"));
		}
		const clientUuid = s.genUuid();
		const row = {
			client_uuid: clientUuid,
			task: taskName,
			blob: blob,
			mime_type: blob.type,
			filename: filename || clientUuid + ".jpg",
			captured_at: Date.now(),
			upload_status: "pending",
		};
		return store.put("evidence", row).then(function () {
			return maybeSyncTaskPhotos();
		});
	}

	// Guards against two overlapping runs (e.g. the `online` listener firing
	// again while a previous upload is still in flight) each picking up the
	// same still-`pending` evidence row and uploading/attaching it twice
	// before either finishes and removes it.
	let taskPhotoSyncInFlight = false;

	function maybeSyncTaskPhotos() {
		const store = db();
		const s = sync();
		if (!store || !s || !isOnline() || taskPhotoSyncInFlight) {
			return Promise.resolve();
		}
		taskPhotoSyncInFlight = true;
		return store
			.getAll("evidence")
			.then(function (rows) {
				const pending = (rows || []).filter(function (r) {
					return r.upload_status === "pending" && r.task;
				});
				// Claim each row (mark "uploading") before the async upload starts,
				// as a second line of defense against a second tab on the same
				// origin racing this same evidence store.
				return Promise.all(
					pending.map(function (row) {
						row.upload_status = "uploading";
						return store.put("evidence", row);
					})
				).then(function () {
					return pending.reduce(function (chain, row) {
						return chain.then(function () {
							return s
								.uploadEvidenceFile(row.client_uuid, row.filename, row.blob, null, {
									doctype: "Task",
									docname: row.task,
								})
								.then(function (fileUrl) {
									return s
										.queueOperation(
											"task.upload_task_photo",
											{ task: row.task, file_url: fileUrl, filename: row.filename },
											{ task: row.task }
										)
										.then(function () {
											return store.remove("evidence", row.client_uuid);
										});
								})
								.catch(function (err) {
									console.warn("Task photo upload failed (will retry):", err);
									row.upload_status = "pending";
									return store.put("evidence", row);
								});
						});
					}, Promise.resolve());
				});
			})
			.finally(function () {
				taskPhotoSyncInFlight = false;
			});
	}

	function updateStatusPill($wrap, syncing, knownOffline) {
		if (!$wrap || !$wrap.length) {
			return;
		}
		let $pill = $wrap.find(".my-tasks-offline-pill");
		if (!$pill.length) {
			$pill = $(
				'<span class="my-tasks-offline-pill badge" style="margin-left:8px;"></span>'
			);
			$wrap.find(".my-tasks-header-right").prepend($pill);
		}
		$pill.removeClass("badge-success badge-danger badge-warning");
		// navigator.onLine alone is unreliable under DevTools throttling profiles
		// (it doesn't always flip). Trust a real failed request (knownOffline) too.
		if (syncing) {
			$pill.addClass("badge-warning").text(__("Syncing…"));
		} else if (!isOnline() || knownOffline) {
			$pill.addClass("badge-danger").text(__("Offline"));
		} else {
			$pill.addClass("badge-success").text(__("Online"));
		}
	}

	function precacheDeskAssets() {
		if (!("caches" in window) || !window.isSecureContext) {
			return;
		}
		const urls = [
			location.pathname,
			"/app/my-tasks",
			"/desk/my-tasks",
			"/my_tasks_desk_offline",
			"/assets/fitzgerald_kitchens/offline/db.js",
			"/assets/fitzgerald_kitchens/offline/sync.js",
			"/assets/fitzgerald_kitchens/js/my_tasks_offline.js",
			"/assets/fitzgerald_kitchens/js/task_camera.js",
		];
		caches.open(CACHE_NAME_SAFE()).then(function (cache) {
			urls.forEach(function (url) {
				cache.add(url).catch(function () {});
			});
		});
	}

	function CACHE_NAME_SAFE() {
		// Must match CACHE_NAME in www/offline_sw.js — the SW's activate handler
		// deletes any cache key that isn't its own, wiping this precache otherwise.
		return "fk-offline-shell-v10";
	}

	function registerSW() {
		if (!window.isSecureContext || !("serviceWorker" in navigator)) {
			return;
		}
		navigator.serviceWorker.register("/offline_sw.js", { scope: "/" }).then(function () {
			precacheDeskAssets();
		}).catch(function (err) {
			console.warn("FK offline SW register from Desk failed", err);
		});
	}

	window.addEventListener("online", function () {
		maybeSyncTaskPhotos();
	});

	global.fkDeskMyTasksOffline = {
		isOnline: isOnline,
		getOutboxSummary: getOutboxSummary,
		saveDashboard: saveDashboard,
		loadDashboard: loadDashboard,
		queueTaskOperation: queueTaskOperation,
		queueComplete: queueComplete,
		queueProgress: queueProgress,
		queueTimerAction: queueTimerAction,
		queueDespatch: queueDespatch,
		queueTaskPhoto: queueTaskPhoto,
		syncOutbox: syncOutbox,
		updateStatusPill: updateStatusPill,
		registerSW: registerSW,
		precacheDeskAssets: precacheDeskAssets,
	};
})(window);
