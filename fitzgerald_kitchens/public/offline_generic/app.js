// Generic Offline Sync UI: DocType list → document list → create/edit form.
(function () {
	"use strict";

	const db = window.osOfflineDB;
	const sync = window.osOfflineSync;

	// crypto.randomUUID is only exposed in secure contexts (https, or
	// localhost/127.0.0.1/*.localhost); fall back to a plain UUID v4 elsewhere.
	function genUuid() {
		if (window.crypto && typeof window.crypto.randomUUID === "function") {
			return window.crypto.randomUUID();
		}
		return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
			const r = (Math.random() * 16) | 0;
			const v = c === "x" ? r : (r & 0x3) | 0x8;
			return v.toString(16);
		});
	}

	const els = {
		status: document.getElementById("os-sync-status"),
		statusText: document.getElementById("os-sync-status-text"),
		hint: document.getElementById("os-hint"),
		homeNav: document.getElementById("os-home-nav"),
		doctypeList: document.getElementById("os-doctype-list"),
		homePanel: document.getElementById("os-home-panel"),
		tasksPanel: document.getElementById("os-tasks-panel"),
		tasksList: document.getElementById("os-tasks-list"),
		listPanel: document.getElementById("os-list-panel"),
		formPanel: document.getElementById("os-form-panel"),
		listTitle: document.getElementById("os-list-title"),
		docList: document.getElementById("os-doc-list"),
		newDoc: document.getElementById("os-new-doc"),
		formTitle: document.getElementById("os-form-title"),
		form: document.getElementById("os-form"),
		formError: document.getElementById("os-form-error"),
		outboxList: document.getElementById("os-outbox-list"),
		refresh: document.getElementById("os-refresh"),
		syncNow: document.getElementById("os-sync-now"),
		retryFailed: document.getElementById("os-retry-failed"),
		backHome: document.getElementById("os-back-home"),
		backHomeTasks: document.getElementById("os-back-home-tasks"),
		backList: document.getElementById("os-back-list"),
		saveDoc: document.getElementById("os-save-doc"),
	};

	let config = null;
	let currentDoctype = null;
	let currentDoc = null;
	let isCreate = false;

	function escapeHtml(value) {
		const div = document.createElement("div");
		div.textContent = value == null ? "" : String(value);
		return div.innerHTML;
	}

	function showPanel(panel) {
		els.homePanel.classList.toggle("os-hidden", panel !== "home");
		els.listPanel.classList.toggle("os-hidden", panel !== "list");
		els.formPanel.classList.toggle("os-hidden", panel !== "form");
		if (els.tasksPanel) {
			els.tasksPanel.classList.toggle("os-hidden", panel !== "tasks");
		}
	}

	function doctypeConfig(doctype) {
		if (!config || !config.doctypes) {
			return null;
		}
		return config.doctypes.find(function (row) {
			return row.doctype === doctype;
		});
	}

	function updateStatus() {
		const online = navigator.onLine;
		const syncing = sync.isSyncing();
		els.status.classList.remove("online", "offline", "syncing", "auth");
		if (sync.isAuthRequired && sync.isAuthRequired()) {
			els.status.classList.add("auth");
			els.statusText.innerHTML =
				'Session expired — <a href="/login?redirect-to=/offline">log in</a>';
		} else if (syncing) {
			els.status.classList.add("syncing");
			els.statusText.textContent = "Syncing…";
		} else if (online) {
			els.status.classList.add("online");
			els.statusText.textContent = "Online";
		} else {
			els.status.classList.add("offline");
			els.statusText.textContent = "Offline";
		}
	}

	function renderOutbox() {
		return db.getAll("outbox").then(function (rows) {
			if (!rows.length) {
				els.outboxList.innerHTML = '<div class="os-empty">Nothing queued.</div>';
				return;
			}
			rows.sort(function (a, b) {
				return b.created_at - a.created_at;
			});
			els.outboxList.innerHTML = "";
			rows.forEach(function (row) {
				const wrap = document.createElement("div");
				wrap.className = "os-out-wrap";

				const label =
					row.operation +
					" · " +
					((row.payload &&
						(row.payload.doctype ||
							row.payload.name ||
							row.payload.task ||
							row.payload.task_name)) ||
						"");
				const el = document.createElement("div");
				el.className = "os-out-row";
				el.innerHTML =
					"<span>" +
					escapeHtml(label) +
					'</span><span class="os-badge">' +
					escapeHtml(row.status) +
					(row.error ? " — " + escapeHtml(row.error) : "") +
					"</span>";
				wrap.appendChild(el);

				const actions = document.createElement("div");
				actions.className = "os-out-actions";

				if (row.status === "failed") {
					const retryBtn = document.createElement("button");
					retryBtn.type = "button";
					retryBtn.className = "os-small";
					retryBtn.textContent = "Retry";
					retryBtn.addEventListener("click", function () {
						sync.retryOperation(row.client_uuid).then(function () {
							return renderOutbox();
						});
					});
					const discardBtn = document.createElement("button");
					discardBtn.type = "button";
					discardBtn.className = "os-small os-secondary";
					discardBtn.textContent = "Discard";
					discardBtn.addEventListener("click", function () {
						sync.discardOperation(row.client_uuid).then(renderOutbox);
					});
					actions.appendChild(retryBtn);
					actions.appendChild(discardBtn);
				}

				if (row.status === "conflict") {
					const canRetryServer =
						row.payload &&
						row.payload.based_on_modified !== undefined &&
						row.conflict_state &&
						row.conflict_state.modified;
					if (canRetryServer) {
						const useServerBtn = document.createElement("button");
						useServerBtn.type = "button";
						useServerBtn.className = "os-small";
						useServerBtn.textContent = "Use server & retry";
						useServerBtn.addEventListener("click", function () {
							sync.resolveConflict(row.client_uuid, "retry_with_server_state").then(function () {
								return renderOutbox();
							});
						});
						actions.appendChild(useServerBtn);
					}
					const discardRefreshBtn = document.createElement("button");
					discardRefreshBtn.type = "button";
					discardRefreshBtn.className = "os-small os-secondary";
					discardRefreshBtn.textContent = "Discard & refresh";
					discardRefreshBtn.addEventListener("click", function () {
						sync.resolveConflict(row.client_uuid, "discard").then(function () {
							return renderOutbox();
						});
					});
					actions.appendChild(discardRefreshBtn);
				}

				if (actions.childNodes.length) {
					wrap.appendChild(actions);
				}
				els.outboxList.appendChild(wrap);
			});
		});
	}

	function renderHome() {
		if (!config || !config.enabled) {
			els.hint.innerHTML =
				"Offline Sync is not ready. In Desk open " +
				'<a href="/app/offline-sync-settings">Offline Sync Settings</a>, ' +
				"click <strong>Apply Phase 1 Defaults</strong> (or add DocTypes / My Tasks), then Sync here.";
			if (els.homeNav) {
				els.homeNav.innerHTML = "";
			}
			els.doctypeList.innerHTML =
				'<div class="os-empty">Desk stays online-only — field work uses this /offline app.</div>';
			return Promise.resolve();
		}

		const hasDoctypes = config.doctypes && config.doctypes.length;
		// My Tasks intentionally does NOT render here. It has its own local
		// cache/outbox on the Desk page (/app/my-tasks) — showing it here too,
		// with a SEPARATE IndexedDB cache and outbox, caused real confusion:
		// actions queued on one page were invisible on the other. My Tasks
		// lives only on /app/my-tasks now; this page stays generic DocTypes.
		const hasMyTasks = false;
		els.hint.textContent =
			"Local-first: data lives in IndexedDB. Sync while online; work with no lag offline.";

		return Promise.all([db.getAll("docs"), db.getAll("tasks_cache")]).then(function (results) {
			const docs = results[0] || [];
			const tasks = results[1] || [];
			const counts = {};
			docs.forEach(function (row) {
				if (row && row.doctype) {
					counts[row.doctype] = (counts[row.doctype] || 0) + 1;
				}
			});
			const openTasks = tasks.filter(function (t) {
				return t && t._bucket !== "completed" && t.status !== "Completed";
			}).length;

			let navHtml = "";
			if (hasMyTasks) {
				navHtml +=
					'<div class="os-row os-nav-row" data-nav="tasks"><div><strong>My Tasks</strong>' +
					'<span class="os-count">' +
					openTasks +
					"</span><span>Complete / despatch offline</span></div></div>";
			}
			if (els.homeNav) {
				els.homeNav.innerHTML = navHtml;
				els.homeNav.querySelectorAll("[data-nav=tasks]").forEach(function (rowEl) {
					rowEl.addEventListener("click", openMyTasks);
				});
			}

			if (!hasDoctypes) {
				els.doctypeList.innerHTML = hasMyTasks
					? ""
					: '<div class="os-empty">No DocTypes configured. Add Customer / ToDo in Settings.</div>';
				return;
			}

			els.doctypeList.innerHTML =
				'<div class="os-section-label">DocTypes</div>' +
				config.doctypes
					.map(function (row) {
						const n = counts[row.doctype] || 0;
						return (
							'<div class="os-row" data-doctype="' +
							escapeHtml(row.doctype) +
							'"><div><strong>' +
							escapeHtml(row.doctype) +
							'</strong><span class="os-count">' +
							n +
							"</span><span>" +
							(row.allow_create ? "Create" : "No create") +
							" · " +
							(row.allow_write ? "Edit" : "No edit") +
							"</span></div></div>"
						);
					})
					.join("");

			els.doctypeList.querySelectorAll("[data-doctype]").forEach(function (rowEl) {
				rowEl.addEventListener("click", function () {
					openDoctype(rowEl.getAttribute("data-doctype"));
				});
			});
		});
	}

	function renderDoctypes() {
		return renderHome();
	}

	function openMyTasks() {
		showPanel("tasks");
		return renderTasks();
	}

	function outboxStatusFor(outbox, matchFn) {
		let best = null;
		outbox.forEach(function (row) {
			if (matchFn(row)) {
				best = row;
			}
		});
		return best;
	}

	function renderTasks() {
		if (!els.tasksList) {
			return Promise.resolve();
		}
		return Promise.all([db.getAll("tasks_cache"), db.getAll("outbox")]).then(function (results) {
			const tasks = results[0] || [];
			const outbox = results[1] || [];
			const open = tasks.filter(function (t) {
				return t && t._bucket !== "completed" && t.status !== "Completed";
			});

			if (!open.length) {
				els.tasksList.innerHTML =
					'<div class="os-empty">No open tasks cached. Sync while online to load My Tasks.</div>';
				return;
			}

			els.tasksList.innerHTML = "";
			open.forEach(function (task) {
				const row = document.createElement("div");
				row.className = "os-task-row";

				const info = document.createElement("div");
				info.innerHTML =
					'<div class="os-task-name">' +
					escapeHtml(task.subject || task.name) +
					"</div>" +
					'<div class="os-task-sub">' +
					escapeHtml(task.name) +
					(task.project ? " · " + escapeHtml(task.project) : "") +
					"</div>";
				row.appendChild(info);

				const completeOp = outboxStatusFor(outbox, function (r) {
					return r.operation === "task.complete_task" && r.payload && r.payload.task === task.name;
				});
				const despatchOp = outboxStatusFor(outbox, function (r) {
					return (
						r.operation === "despatch.submit_despatch_material_request" &&
						r.payload &&
						r.payload.task_name === task.name
					);
				});

				const actions = document.createElement("div");
				actions.className = "os-task-actions";

				if (completeOp) {
					const badge = document.createElement("span");
					badge.className = "os-badge";
					badge.textContent =
						completeOp.status === "pending"
							? "Completing…"
							: completeOp.status === "failed"
								? "Complete failed"
								: completeOp.status;
					actions.appendChild(badge);
				} else if (task._pending_complete) {
					const badge = document.createElement("span");
					badge.className = "os-badge";
					badge.textContent = "Completing…";
					actions.appendChild(badge);
				} else {
					const completeBtn = document.createElement("button");
					completeBtn.type = "button";
					completeBtn.className = "os-small";
					completeBtn.textContent = "Complete";
					completeBtn.addEventListener("click", function () {
						completeTask(task.name);
					});
					actions.appendChild(completeBtn);

					const despatchBtn = document.createElement("button");
					despatchBtn.type = "button";
					despatchBtn.className = "os-small os-secondary";
					despatchBtn.textContent = despatchOp ? "Despatch queued" : "Despatch";
					despatchBtn.disabled = !!despatchOp;
					despatchBtn.addEventListener("click", function () {
						queueDespatch(task.name);
					});
					actions.appendChild(despatchBtn);
				}

				row.appendChild(actions);
				els.tasksList.appendChild(row);
			});
		});
	}

	function completeTask(taskName) {
		return db
			.get("tasks_cache", taskName)
			.then(function (task) {
				if (task) {
					task.status = "Completed";
					task._bucket = "completed";
					task._pending_complete = true;
					return db.put("tasks_cache", task);
				}
			})
			.then(function () {
				return sync.queueOperation("task.complete_task", { task: taskName });
			})
			.then(function () {
				return renderTasks();
			});
	}

	function queueDespatch(taskName) {
		return sync
			.queueOperation("despatch.submit_despatch_material_request", { task_name: taskName })
			.then(function () {
				return renderTasks();
			});
	}

	function openDoctype(doctype) {
		currentDoctype = doctype;
		const cfg = doctypeConfig(doctype);
		els.listTitle.textContent = doctype;
		els.newDoc.classList.toggle("os-hidden", !(cfg && cfg.allow_create));
		showPanel("list");
		return renderDocList();
	}

	function renderDocList() {
		return db.getAllByIndex("docs", "doctype", currentDoctype).then(function (rows) {
			rows = rows.filter(function (row) {
				return !(row.name && String(row.name).indexOf("__local_") === 0);
			});
			// Also include pending local creates
			return db.getAll("docs").then(function (all) {
				const locals = all.filter(function (row) {
					return (
						row.doctype === currentDoctype &&
						row.name &&
						String(row.name).indexOf("__local_") === 0
					);
				});
				const combined = rows.concat(locals);
				combined.sort(function (a, b) {
					return String(b.modified || "").localeCompare(String(a.modified || ""));
				});
				if (!combined.length) {
					els.docList.innerHTML =
						'<div class="os-empty">No cached documents. Sync while online to download.</div>';
					return;
				}
				els.docList.innerHTML = combined
					.map(function (row) {
						return (
							'<div class="os-row" data-id="' +
							escapeHtml(row.id) +
							'"><div><strong>' +
							escapeHtml(row.title || row.name) +
							"</strong><span>" +
							escapeHtml(row.name) +
							"</span></div></div>"
						);
					})
					.join("");
				els.docList.querySelectorAll(".os-row").forEach(function (rowEl) {
					rowEl.addEventListener("click", function () {
						openDoc(rowEl.getAttribute("data-id"));
					});
				});
			});
		});
	}

	function fieldInputHtml(field, value) {
		const name = field.fieldname;
		const reqd = field.reqd ? " required" : "";
		const readonly = field.read_only ? " disabled" : "";
		const val = value == null ? "" : value;

		if (field.fieldtype === "Check") {
			return (
				'<div class="os-field"><label><input type="checkbox" name="' +
				escapeHtml(name) +
				'"' +
				(val ? " checked" : "") +
				readonly +
				"> " +
				escapeHtml(field.label) +
				"</label></div>"
			);
		}

		if (field.fieldtype === "Select" && field.options) {
			const options = String(field.options)
				.split("\n")
				.filter(Boolean)
				.map(function (opt) {
					return (
						'<option value="' +
						escapeHtml(opt) +
						'"' +
						(String(val) === opt ? " selected" : "") +
						">" +
						escapeHtml(opt) +
						"</option>"
					);
				})
				.join("");
			return (
				'<div class="os-field"><label>' +
				escapeHtml(field.label) +
				'</label><select name="' +
				escapeHtml(name) +
				'"' +
				reqd +
				readonly +
				"><option value=\"\"></option>" +
				options +
				"</select></div>"
			);
		}

		if (field.fieldtype === "Text" || field.fieldtype === "Small Text" || field.fieldtype === "Long Text" || field.fieldtype === "Text Editor") {
			return (
				'<div class="os-field"><label>' +
				escapeHtml(field.label) +
				'</label><textarea name="' +
				escapeHtml(name) +
				'"' +
				reqd +
				readonly +
				">" +
				escapeHtml(val) +
				"</textarea></div>"
			);
		}

		let type = "text";
		if (field.fieldtype === "Date") {
			type = "date";
		} else if (field.fieldtype === "Datetime") {
			type = "datetime-local";
		} else if (field.fieldtype === "Time") {
			type = "time";
		} else if (field.fieldtype === "Int" || field.fieldtype === "Float" || field.fieldtype === "Currency" || field.fieldtype === "Percent") {
			type = "number";
		}

		let displayVal = val;
		if (field.fieldtype === "Datetime" && val) {
			displayVal = String(val).replace(" ", "T").slice(0, 16);
		}

		return (
			'<div class="os-field"><label>' +
			escapeHtml(field.label) +
			'</label><input type="' +
			type +
			'" name="' +
			escapeHtml(name) +
			'" value="' +
			escapeHtml(displayVal) +
			'"' +
			reqd +
			readonly +
			"></div>"
		);
	}

	function buildForm(cfg, doc) {
		els.form.innerHTML = (cfg.fields || [])
			.map(function (field) {
				return fieldInputHtml(field, doc ? doc[field.fieldname] : "");
			})
			.join("");
		els.formError.classList.add("os-hidden");
		els.formError.textContent = "";
	}

	function openDoc(id) {
		return db.get("docs", id).then(function (row) {
			if (!row) {
				return;
			}
			const cfg = doctypeConfig(row.doctype);
			if (!cfg) {
				return;
			}
			currentDoctype = row.doctype;
			currentDoc = row;
			isCreate = false;
			els.formTitle.textContent = row.title || row.name;
			els.saveDoc.classList.toggle("os-hidden", !cfg.allow_write);
			buildForm(cfg, row.doc || {});
			showPanel("form");
		});
	}

	function openNew() {
		const cfg = doctypeConfig(currentDoctype);
		if (!cfg || !cfg.allow_create) {
			return;
		}
		isCreate = true;
		currentDoc = null;
		els.formTitle.textContent = "New " + currentDoctype;
		els.saveDoc.classList.remove("os-hidden");
		buildForm(cfg, {});
		showPanel("form");
	}

	function readFormValues(cfg) {
		const data = { doctype: currentDoctype };
		(cfg.fields || []).forEach(function (field) {
			if (field.read_only) {
				return;
			}
			const input = els.form.elements.namedItem(field.fieldname);
			if (!input) {
				return;
			}
			if (field.fieldtype === "Check") {
				data[field.fieldname] = input.checked ? 1 : 0;
			} else if (field.fieldtype === "Datetime" && input.value) {
				data[field.fieldname] = input.value.replace("T", " ") + ":00";
			} else {
				data[field.fieldname] = input.value;
			}
		});
		return data;
	}

	function saveCurrent() {
		const cfg = doctypeConfig(currentDoctype);
		if (!cfg) {
			return;
		}
		const values = readFormValues(cfg);
		els.formError.classList.add("os-hidden");

		if (isCreate) {
			const localName = "__local_" + genUuid();
			const localId = db.docId(currentDoctype, localName);
			const localDoc = Object.assign({}, values, {
				name: localName,
				_title: values[cfg.title_field] || localName,
			});
			return db
				.put("docs", {
					id: localId,
					doctype: currentDoctype,
					name: localName,
					title: localDoc._title,
					modified: new Date().toISOString(),
					doc: localDoc,
				})
				.then(function () {
					return sync.queueOperation("doc.insert", {
						doctype: currentDoctype,
						doc: values,
						_local_id: localId,
					});
				})
				.then(function () {
					showPanel("list");
					return renderDocList();
				});
		}

		if (!currentDoc || !cfg.allow_write) {
			return;
		}

		const name = currentDoc.name;
		const basedOn = currentDoc.modified || (currentDoc.doc && currentDoc.doc.modified);
		const merged = Object.assign({}, currentDoc.doc || {}, values, { name: name });
		return db
			.put("docs", {
				id: currentDoc.id,
				doctype: currentDoctype,
				name: name,
				title: merged[cfg.title_field] || merged._title || name,
				modified: basedOn,
				doc: merged,
			})
			.then(function () {
				return sync.queueOperation("doc.save", {
					doctype: currentDoctype,
					name: name,
					doc: values,
					based_on_modified: basedOn,
				});
			})
			.then(function () {
				showPanel("list");
				return renderDocList();
			})
			.catch(function (err) {
				els.formError.textContent = String(err && err.message ? err.message : err);
				els.formError.classList.remove("os-hidden");
			});
	}

	function refreshAll(fullPull) {
		updateStatus();
		return sync
			.fetchConfig()
			.then(function (cfg) {
				config = cfg;
				return renderHome().then(function () {
					return sync.pullNow(!!fullPull);
				});
			})
			.then(function () {
				return renderHome();
			})
			.then(function () {
				if (els.tasksPanel && !els.tasksPanel.classList.contains("os-hidden")) {
					return renderTasks();
				}
			})
			.then(function () {
				return renderOutbox();
			})
			.then(function () {
				if (currentDoctype && !els.listPanel.classList.contains("os-hidden")) {
					return renderDocList();
				}
			})
			.catch(function (err) {
				console.warn(err);
				els.hint.textContent = "Could not refresh. Showing cached data if available.";
				return sync.fetchConfig().then(function (cfg) {
					config = cfg;
					return renderHome().then(renderOutbox);
				});
			});
	}

	els.refresh.addEventListener("click", function () {
		refreshAll(true);
	});
	els.syncNow.addEventListener("click", function () {
		sync
			.syncNow()
			.then(function () {
				return sync.pullNow();
			})
			.then(function () {
				return renderOutbox();
			})
			.then(function () {
				if (els.tasksPanel && !els.tasksPanel.classList.contains("os-hidden")) {
					return renderTasks();
				}
			});
	});
	if (els.retryFailed) {
		els.retryFailed.addEventListener("click", function () {
			sync.retryAllFailed().then(renderOutbox);
		});
	}
	els.backHome.addEventListener("click", function () {
		currentDoctype = null;
		showPanel("home");
		renderHome();
	});
	if (els.backHomeTasks) {
		els.backHomeTasks.addEventListener("click", function () {
			showPanel("home");
			renderHome();
		});
	}
	els.backList.addEventListener("click", function () {
		showPanel("list");
		renderDocList();
	});
	els.newDoc.addEventListener("click", openNew);
	els.saveDoc.addEventListener("click", function (event) {
		event.preventDefault();
		saveCurrent();
	});
	els.form.addEventListener("submit", function (event) {
		event.preventDefault();
		saveCurrent();
	});

	window.addEventListener("online", updateStatus);
	window.addEventListener("offline", updateStatus);
	sync.onChange(function () {
		updateStatus();
		renderOutbox();
		if (currentDoctype && !els.listPanel.classList.contains("os-hidden")) {
			renderDocList();
		}
		if (els.tasksPanel && !els.tasksPanel.classList.contains("os-hidden")) {
			renderTasks();
		}
	});

	updateStatus();
	showPanel("home");
	refreshAll(false).then(function () {
		sync.maybeSyncNow();
	});
})();
