// Offline app shell UI: My Tasks (complete/despatch), Scan Label, and
// Development Units (stage start/complete, labour/material/issue entries,
// evidence photo capture). Reads/writes IndexedDB via db.js and queues every
// write via sync.js — this file never talks to the server directly for
// writes, only for the read-only dashboard/pull refresh.
(function () {
	"use strict";

	const db = window.fkOfflineDB;
	const sync = window.fkOfflineSync;

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

	const DASHBOARD_URL =
		"/api/method/fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.my_tasks.get_my_tasks_dashboard";
	const CATALOG_URL =
		"/api/method/fitzgerald_kitchens.fitzgerald_kitchens.doctype.offline_sync_settings.offline_sync_settings.get_enabled_catalog";

	const tasksListEl = document.getElementById("fk-tasks-list");
	const unitsListEl = document.getElementById("fk-units-list");
	const outboxListEl = document.getElementById("fk-outbox-list");
	const statusEl = document.getElementById("fk-sync-status");
	const statusTextEl = document.getElementById("fk-sync-status-text");
	const refreshBtn = document.getElementById("fk-refresh-tasks");
	const syncNowBtn = document.getElementById("fk-sync-now");
	const retryFailedBtn = document.getElementById("fk-retry-failed");
	const scanTaskInput = document.getElementById("fk-scan-task");
	const scanQrInput = document.getElementById("fk-scan-qr");
	const scanSubmitBtn = document.getElementById("fk-scan-submit");

	// ui_section keys from Offline Sync Settings catalog (null = show all / legacy)
	let enabledSections = null;

	function csrfToken() {
		const meta = document.querySelector('meta[name="csrf-token"]');
		return meta ? meta.getAttribute("content") : "";
	}

	function escapeHtml(value) {
		const div = document.createElement("div");
		div.textContent = value == null ? "" : String(value);
		return div.innerHTML;
	}

	function sectionEnabled(name) {
		if (!enabledSections) {
			return true;
		}
		return enabledSections.indexOf(name) !== -1;
	}

	function applySectionVisibility() {
		document.querySelectorAll("[data-ui-section]").forEach(function (el) {
			const key = el.getAttribute("data-ui-section");
			el.style.display = sectionEnabled(key) ? "" : "none";
		});
	}

	function loadEnabledCatalog() {
		if (!navigator.onLine) {
			return Promise.resolve();
		}
		return fetch(CATALOG_URL + "?app_name=" + encodeURIComponent("fitzgerald_kitchens"), {
			credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrfToken() },
		})
			.then(function (resp) {
				return resp.ok ? resp.json() : null;
			})
			.then(function (data) {
				const message = data && data.message;
				if (!message) {
					return;
				}
				if (!message.enabled) {
					enabledSections = null;
					return;
				}
				enabledSections = (message.items || [])
					.map(function (item) {
						return item.ui_section;
					})
					.filter(Boolean);
			})
			.catch(function () {
				/* keep previous / show all */
			})
			.then(applySectionVisibility);
	}

	// ---------------------------------------------------------------- Tasks

	function refreshTasksFromServer() {
		if (!navigator.onLine) {
			return Promise.resolve();
		}
		return fetch(DASHBOARD_URL, {
			credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrfToken() },
		})
			.then(function (resp) {
				return resp.ok ? resp.json() : null;
			})
			.then(function (data) {
				const message = data && data.message;
				if (!message || !message.tabs) {
					return;
				}
				const rows = [];
				Object.keys(message.tabs).forEach(function (bucket) {
					(message.tabs[bucket].tasks || []).forEach(function (task) {
						rows.push(Object.assign({}, task, { _bucket: bucket }));
					});
				});
				return Promise.all(
					rows.map(function (row) {
						return db.put("tasks_cache", row);
					})
				);
			})
			.catch(function (err) {
				console.warn("Could not refresh tasks from server:", err);
			});
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
		return Promise.all([db.getAll("tasks_cache"), db.getAll("outbox")]).then(function (results) {
			const tasks = results[0];
			const outbox = results[1];

			if (!tasks.length) {
				tasksListEl.innerHTML = '<div class="fk-empty">No tasks cached yet — connect once online to load your task list.</div>';
				return;
			}

			tasksListEl.innerHTML = "";
			tasks
				.filter(function (t) {
					return t._bucket !== "completed" && t.status !== "Completed";
				})
				.forEach(function (task) {
					const row = document.createElement("div");
					row.className = "fk-task-row";

					const info = document.createElement("div");
					info.innerHTML =
						'<div class="fk-task-name">' + escapeHtml(task.subject || task.name) + "</div>" +
						'<div class="fk-task-sub">' + escapeHtml(task.name) + "</div>";
					row.appendChild(info);

					const completeOp = outboxStatusFor(outbox, function (r) {
						return r.operation === "task.complete_task" && r.payload.task === task.name;
					});

					const actions = document.createElement("div");
					actions.style.display = "flex";
					actions.style.gap = "0.4rem";
					actions.style.alignItems = "center";

					if (completeOp) {
						const badge = document.createElement("span");
						badge.className = "fk-badge " + (completeOp.status === "pending" ? "pending" : completeOp.status);
						badge.textContent =
							completeOp.status === "pending" ? "Waiting to sync" : completeOp.status === "failed" ? "Sync failed" : completeOp.status;
						actions.appendChild(badge);
					} else {
						const completeBtn = document.createElement("button");
						completeBtn.className = "fk-small";
						completeBtn.textContent = "Complete";
						completeBtn.addEventListener("click", function () {
							completeTask(task.name);
						});
						actions.appendChild(completeBtn);

						const despatchBtn = document.createElement("button");
						despatchBtn.className = "fk-small fk-secondary";
						despatchBtn.textContent = "Despatch";
						despatchBtn.title = "Queues despatch — only finalized once online (creates a real stock movement).";
						despatchBtn.addEventListener("click", function () {
							queueDespatch(task.name);
						});
						actions.appendChild(despatchBtn);
					}

					row.appendChild(actions);
					tasksListEl.appendChild(row);
				});

			if (!tasksListEl.children.length) {
				tasksListEl.innerHTML = '<div class="fk-empty">Nothing outstanding.</div>';
			}
		});
	}

	function completeTask(taskName) {
		sync.queueOperation("task.complete_task", { task: taskName }, { task: taskName }).then(renderAll);
	}

	function queueDespatch(taskName) {
		sync
			.queueOperation("despatch.submit_despatch_material_request", { task_name: taskName }, { task: taskName })
			.then(renderAll);
	}

	function submitScan() {
		const taskName = (scanTaskInput.value || "").trim();
		const qrText = (scanQrInput.value || "").trim();
		if (!taskName || !qrText) {
			return;
		}
		sync
			.queueOperation(
				"label_scan.record_task_label_scan",
				{ task_name: taskName, qr_text: qrText },
				{ task: taskName }
			)
			.then(function () {
				scanQrInput.value = "";
				renderAll();
			});
	}

	// ------------------------------------------------------ Development Units

	function renderUnits() {
		return Promise.all([db.getAll("development_units"), db.getAll("outbox")]).then(function (results) {
			const units = results[0];
			const outbox = results[1];

			if (!units.length) {
				unitsListEl.innerHTML = '<div class="fk-empty">No units cached yet — connect once online to load your assigned units.</div>';
				return;
			}

			unitsListEl.innerHTML = "";
			units.forEach(function (unit) {
				unitsListEl.appendChild(renderUnitCard(unit, outbox));
			});
		});
	}

	function renderUnitCard(unit, outbox) {
		const card = document.createElement("div");
		card.className = "fk-unit-card";

		const title = document.createElement("div");
		title.className = "fk-unit-title";
		title.textContent = unit.unit_reference || unit.name;
		card.appendChild(title);

		const sub = document.createElement("div");
		sub.className = "fk-unit-sub";
		sub.textContent = unit.name + " — " + (unit.current_stage || "No stage") + " (" + (unit.current_stage_progress || 0) + "%)";
		card.appendChild(sub);

		(unit.stages || []).forEach(function (stage) {
			card.appendChild(renderStageRow(unit, stage, outbox));
		});

		card.appendChild(renderUnitActions(unit));

		return card;
	}

	function renderStageRow(unit, stage, outbox) {
		const row = document.createElement("div");
		row.className = "fk-stage-row";

		const stageOp = outboxStatusFor(outbox, function (r) {
			return (
				(r.operation === "development_unit.start_stage" || r.operation === "development_unit.complete_stage") &&
				r.payload.development_unit === unit.name &&
				r.payload.stage_row_name === stage.name
			);
		});

		const info = document.createElement("div");
		info.className = "fk-stage-name";
		info.textContent = stage.stage + " — " + stage.status;
		row.appendChild(info);

		const actions = document.createElement("div");
		actions.className = "fk-stage-actions";

		if (stageOp && stageOp.status === "conflict") {
			const conflictBtn = document.createElement("span");
			conflictBtn.className = "fk-badge conflict";
			conflictBtn.textContent = "Conflict — refresh";
			conflictBtn.style.cursor = "pointer";
			conflictBtn.title = stageOp.error || "Someone else changed this stage.";
			conflictBtn.addEventListener("click", function () {
				sync.resolveConflict(stageOp.client_uuid, "discard").then(renderAll);
			});
			actions.appendChild(conflictBtn);
		} else if (stageOp) {
			const badge = document.createElement("span");
			badge.className = "fk-badge " + (stageOp.status === "pending" ? "pending" : stageOp.status);
			badge.textContent = stageOp.status === "pending" ? "Waiting to sync" : stageOp.status;
			actions.appendChild(badge);
		} else if (stage.status === "Not Started") {
			const btn = document.createElement("button");
			btn.className = "fk-small";
			btn.textContent = "Start";
			btn.addEventListener("click", function () {
				sync
					.queueOperation(
						"development_unit.start_stage",
						{ development_unit: unit.name, stage_row_name: stage.name, based_on_modified: unit.modified },
						{ development_unit: unit.name, stage: stage.stage }
					)
					.then(renderAll);
			});
			actions.appendChild(btn);
		} else if (stage.status === "Ongoing") {
			const btn = document.createElement("button");
			btn.className = "fk-small";
			btn.textContent = "Complete";
			btn.addEventListener("click", function () {
				sync
					.queueOperation(
						"development_unit.complete_stage",
						{ development_unit: unit.name, stage_row_name: stage.name, based_on_modified: unit.modified },
						{ development_unit: unit.name, stage: stage.stage }
					)
					.then(renderAll);
			});
			actions.appendChild(btn);
		} else {
			const doneLabel = document.createElement("span");
			doneLabel.className = "fk-badge synced";
			doneLabel.textContent = stage.status;
			actions.appendChild(doneLabel);
		}

		row.appendChild(actions);
		return row;
	}

	function renderUnitActions(unit) {
		const wrap = document.createElement("div");

		const actionsRow = document.createElement("div");
		actionsRow.className = "fk-unit-actions";

		const labourBtn = document.createElement("button");
		labourBtn.className = "fk-small fk-secondary";
		labourBtn.textContent = "+ Labour";

		const materialBtn = document.createElement("button");
		materialBtn.className = "fk-small fk-secondary";
		materialBtn.textContent = "+ Material";

		const issueBtn = document.createElement("button");
		issueBtn.className = "fk-small fk-secondary";
		issueBtn.textContent = "+ Issue";

		const evidenceBtn = document.createElement("button");
		evidenceBtn.className = "fk-small fk-secondary";
		evidenceBtn.textContent = "+ Evidence photo";

		actionsRow.appendChild(labourBtn);
		actionsRow.appendChild(materialBtn);
		actionsRow.appendChild(issueBtn);
		actionsRow.appendChild(evidenceBtn);
		wrap.appendChild(actionsRow);

		const labourForm = buildLabourForm(unit);
		const materialForm = buildMaterialForm(unit);
		const issueForm = buildIssueForm(unit);
		const evidenceForm = buildEvidenceForm(unit);

		[labourForm, materialForm, issueForm, evidenceForm].forEach(function (f) {
			wrap.appendChild(f);
		});

		function toggle(form) {
			const wasOpen = form.classList.contains("open");
			[labourForm, materialForm, issueForm, evidenceForm].forEach(function (f) {
				f.classList.remove("open");
			});
			if (!wasOpen) {
				form.classList.add("open");
			}
		}

		labourBtn.addEventListener("click", function () {
			toggle(labourForm);
		});
		materialBtn.addEventListener("click", function () {
			toggle(materialForm);
		});
		issueBtn.addEventListener("click", function () {
			toggle(issueForm);
		});
		evidenceBtn.addEventListener("click", function () {
			toggle(evidenceForm);
		});

		return wrap;
	}

	function firstStageName(unit) {
		return unit.stages && unit.stages.length ? unit.stages[0].stage : "";
	}

	function buildLabourForm(unit) {
		const form = document.createElement("div");
		form.className = "fk-inline-form";
		form.innerHTML =
			'<select class="fk-labour-type">' +
			["Design", "Manufacturing", "Assembly", "Delivery", "Fitting", "Rework", "Other"]
				.map(function (t) {
					return "<option>" + t + "</option>";
				})
				.join("") +
			"</select>" +
			'<input type="number" step="0.25" class="fk-labour-hours" placeholder="Hours">' +
			'<button type="button" class="fk-small fk-labour-submit">Add labour entry</button>';

		form.querySelector(".fk-labour-submit").addEventListener("click", function () {
			const hours = parseFloat(form.querySelector(".fk-labour-hours").value || "0");
			const labourType = form.querySelector(".fk-labour-type").value;
			sync
				.queueOperation(
					"development_unit.record_labour_entry",
					{
						development_unit: unit.name,
						stage: firstStageName(unit),
						start_time: new Date().toISOString(),
						hours: hours || null,
						labour_type: labourType,
					},
					{ development_unit: unit.name }
				)
				.then(function () {
					form.querySelector(".fk-labour-hours").value = "";
					form.classList.remove("open");
					renderAll();
				});
		});
		return form;
	}

	function buildMaterialForm(unit) {
		const form = document.createElement("div");
		form.className = "fk-inline-form";
		form.innerHTML =
			'<input type="text" class="fk-material-item" placeholder="Item code">' +
			'<input type="number" step="0.01" class="fk-material-qty" placeholder="Quantity used">' +
			'<button type="button" class="fk-small fk-material-submit">Add material usage</button>';

		form.querySelector(".fk-material-submit").addEventListener("click", function () {
			const item = (form.querySelector(".fk-material-item").value || "").trim();
			const qty = parseFloat(form.querySelector(".fk-material-qty").value || "0");
			if (!item || !qty) {
				return;
			}
			sync
				.queueOperation(
					"development_unit.record_material_usage",
					{ development_unit: unit.name, item: item, actual_quantity: qty },
					{ development_unit: unit.name }
				)
				.then(function () {
					form.querySelector(".fk-material-item").value = "";
					form.querySelector(".fk-material-qty").value = "";
					form.classList.remove("open");
					renderAll();
				});
		});
		return form;
	}

	function buildIssueForm(unit) {
		const form = document.createElement("div");
		form.className = "fk-inline-form";
		form.innerHTML =
			'<select class="fk-issue-type">' +
			["Defect", "Missing Item", "Damage", "Design Issue", "Site Issue", "Customer Change", "Other"]
				.map(function (t) {
					return "<option>" + t + "</option>";
				})
				.join("") +
			"</select>" +
			'<textarea class="fk-issue-desc" rows="2" placeholder="Describe the issue"></textarea>' +
			'<button type="button" class="fk-small fk-issue-submit">Add issue</button>';

		form.querySelector(".fk-issue-submit").addEventListener("click", function () {
			const description = (form.querySelector(".fk-issue-desc").value || "").trim();
			const issueType = form.querySelector(".fk-issue-type").value;
			if (!description) {
				return;
			}
			sync
				.queueOperation(
					"development_unit.add_issue",
					{ development_unit: unit.name, issue_type: issueType, description: description },
					{ development_unit: unit.name }
				)
				.then(function () {
					form.querySelector(".fk-issue-desc").value = "";
					form.classList.remove("open");
					renderAll();
				});
		});
		return form;
	}

	function buildEvidenceForm(unit) {
		const form = document.createElement("div");
		form.className = "fk-inline-form";

		const video = document.createElement("video");
		video.setAttribute("playsinline", "");
		video.style.width = "100%";
		video.style.borderRadius = "8px";
		video.style.display = "none";

		const startBtn = document.createElement("button");
		startBtn.type = "button";
		startBtn.className = "fk-small";
		startBtn.textContent = "Open camera";

		const captureBtn = document.createElement("button");
		captureBtn.type = "button";
		captureBtn.className = "fk-small";
		captureBtn.textContent = "Capture photo";
		captureBtn.style.display = "none";

		const note = document.createElement("div");
		note.className = "fk-empty";
		note.textContent = "Photo is saved locally immediately, then uploaded when online.";

		let stream = null;

		startBtn.addEventListener("click", function () {
			navigator.mediaDevices
				.getUserMedia({ video: { facingMode: "environment" } })
				.then(function (s) {
					stream = s;
					video.srcObject = s;
					video.style.display = "block";
					video.play();
					captureBtn.style.display = "inline-block";
					startBtn.style.display = "none";
				})
				.catch(function (err) {
					console.warn("Camera unavailable:", err);
					note.textContent = "Camera unavailable on this device/browser.";
				});
		});

		captureBtn.addEventListener("click", function () {
			const canvas = document.createElement("canvas");
			canvas.width = video.videoWidth || 640;
			canvas.height = video.videoHeight || 480;
			canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

			canvas.toBlob(function (blob) {
				if (!blob) {
					return;
				}
				saveEvidenceBlob(unit, firstStageName(unit), blob);
				if (stream) {
					stream.getTracks().forEach(function (track) {
						track.stop();
					});
				}
				video.style.display = "none";
				captureBtn.style.display = "none";
				startBtn.style.display = "inline-block";
				form.classList.remove("open");
				renderAll();
			}, "image/jpeg", 0.85);
		});

		form.appendChild(startBtn);
		form.appendChild(video);
		form.appendChild(captureBtn);
		form.appendChild(note);
		return form;
	}

	function saveEvidenceBlob(unit, stage, blob) {
		const clientUuid = genUuid();
		return db
			.put("evidence", {
				client_uuid: clientUuid,
				development_unit: unit.name,
				stage: stage,
				blob: blob,
				mime_type: blob.type,
				filename: clientUuid + ".jpg",
				captured_at: Date.now(),
				upload_status: "pending",
			})
			.then(function () {
				return maybeSyncEvidence();
			});
	}

	function maybeSyncEvidence() {
		if (!navigator.onLine) {
			return Promise.resolve();
		}
		return db.getAll("evidence").then(function (rows) {
			const pending = rows.filter(function (r) {
				return r.upload_status === "pending";
			});
			return pending.reduce(function (chain, row) {
				return chain.then(function () {
					return sync
						.uploadEvidenceFile(row.client_uuid, row.filename, row.blob, row.development_unit)
						.then(function (fileUrl) {
							row.upload_status = "done";
							row.file_url = fileUrl;
							return db.put("evidence", row).then(function () {
								return sync.queueOperation(
									"development_unit.add_evidence",
									{
										development_unit: row.development_unit,
										stage: row.stage,
										file_url: fileUrl,
										evidence_type: "Other",
									},
									{ development_unit: row.development_unit }
								);
							});
						})
						.catch(function (err) {
							console.warn("Evidence upload failed (will retry):", err);
						});
				});
			}, Promise.resolve());
		});
	}

	// -------------------------------------------------------------- Outbox

	function renderOutbox() {
		return db.getAll("outbox").then(function (rows) {
			if (!rows.length) {
				outboxListEl.innerHTML = '<div class="fk-empty">Nothing queued.</div>';
				return;
			}
			rows.sort(function (a, b) {
				return b.created_at - a.created_at;
			});
			outboxListEl.innerHTML = "";
			rows.forEach(function (row) {
				const wrap = document.createElement("div");
				wrap.className = "fk-out-wrap";

				const el = document.createElement("div");
				el.className = "fk-out-row";
				el.innerHTML =
					"<span>" +
					escapeHtml(row.operation) +
					" — " +
					escapeHtml(JSON.stringify(row.doctype_context || {})) +
					"</span>" +
					'<span class="fk-badge ' +
					row.status +
					'">' +
					row.status +
					"</span>";
				wrap.appendChild(el);

				if (row.error) {
					const note = document.createElement("div");
					note.className = "fk-conflict-note";
					note.textContent = row.error;
					wrap.appendChild(note);
				}

				const actions = document.createElement("div");
				actions.className = "fk-out-actions";

				if (row.status === "failed") {
					const retryBtn = document.createElement("button");
					retryBtn.type = "button";
					retryBtn.className = "fk-small";
					retryBtn.textContent = "Retry";
					retryBtn.addEventListener("click", function () {
						sync.retryOperation(row.client_uuid).then(renderAll);
					});
					const discardBtn = document.createElement("button");
					discardBtn.type = "button";
					discardBtn.className = "fk-small fk-secondary";
					discardBtn.textContent = "Discard";
					discardBtn.addEventListener("click", function () {
						sync.discardOperation(row.client_uuid).then(renderAll);
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
						useServerBtn.className = "fk-small";
						useServerBtn.textContent = "Use server & retry";
						useServerBtn.addEventListener("click", function () {
							sync.resolveConflict(row.client_uuid, "retry_with_server_state").then(renderAll);
						});
						actions.appendChild(useServerBtn);
					}
					const discardRefreshBtn = document.createElement("button");
					discardRefreshBtn.type = "button";
					discardRefreshBtn.className = "fk-small fk-secondary";
					discardRefreshBtn.textContent = "Discard & refresh";
					discardRefreshBtn.addEventListener("click", function () {
						sync.resolveConflict(row.client_uuid, "discard").then(renderAll);
					});
					actions.appendChild(discardRefreshBtn);
				}

				if (actions.childNodes.length) {
					wrap.appendChild(actions);
				}
				outboxListEl.appendChild(wrap);
			});
		});
	}

	// --------------------------------------------------------------- Status

	function renderSyncStatus() {
		const online = navigator.onLine;
		const syncing = sync.isSyncing();
		statusEl.classList.remove("online", "offline", "syncing", "auth");
		if (sync.isAuthRequired && sync.isAuthRequired()) {
			statusEl.classList.add("auth");
			statusTextEl.innerHTML =
				'Session expired — <a href="/login?redirect-to=/offline_app">log in</a>';
		} else if (syncing) {
			statusEl.classList.add("syncing");
			statusTextEl.textContent = "Syncing...";
		} else if (online) {
			statusEl.classList.add("online");
			statusTextEl.textContent = "Online";
		} else {
			statusEl.classList.add("offline");
			statusTextEl.textContent = "Offline — changes are queued";
		}
	}

	function renderAll() {
		applySectionVisibility();
		renderSyncStatus();
		if (sectionEnabled("tasks")) {
			renderTasks();
		}
		if (sectionEnabled("development_units")) {
			renderUnits();
		}
		renderOutbox();
	}

	refreshBtn.addEventListener("click", function () {
		Promise.all([refreshTasksFromServer(), sync.pullNow()]).then(renderAll);
	});
	syncNowBtn.addEventListener("click", function () {
		sync.syncNow().then(sync.pullNow).then(maybeSyncEvidence).then(renderAll);
	});
	if (retryFailedBtn) {
		retryFailedBtn.addEventListener("click", function () {
			sync.retryAllFailed().then(renderAll);
		});
	}
	scanSubmitBtn.addEventListener("click", submitScan);

	window.addEventListener("online", function () {
		maybeSyncEvidence().then(renderAll);
	});
	window.addEventListener("offline", renderAll);
	sync.onChange(renderAll);

	loadEnabledCatalog()
		.then(function () {
			return Promise.all([refreshTasksFromServer(), sync.pullNow()]);
		})
		.then(maybeSyncEvidence)
		.then(renderAll);
})();
