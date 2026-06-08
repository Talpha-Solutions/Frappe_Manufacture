// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const TASK_SCAN_PAGE_SIZE = 10;
const TASK_SCAN_TASK_STORAGE_KEY = "task_scan_task";

function normalize_task_route_value(value) {
	if (!value) {
		return "";
	}
	if (typeof value === "string") {
		try {
			const parsed = JSON.parse(value);
			if (typeof parsed === "string") {
				return parsed;
			}
		} catch {
			// route param may already be a plain task name
		}
		return value.replace(/^["']|["']$/g, "");
	}
	return String(value);
}

function resolve_task_scan_task_name() {
	const raw =
		frappe.route_options?.task ||
		frappe.utils.get_query_params()?.task ||
		sessionStorage.getItem(TASK_SCAN_TASK_STORAGE_KEY) ||
		"";
	const task_name = normalize_task_route_value(raw);
	if (task_name) {
		sessionStorage.setItem(TASK_SCAN_TASK_STORAGE_KEY, task_name);
	}
	return task_name;
}

frappe.pages["task-scan"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Task Scan"),
		single_column: true,
	});

	frappe.task_scan_page = new TaskScanPage(page);
};

frappe.pages["task-scan"].on_page_show = function () {
	if (!frappe.task_scan_page) {
		return;
	}
	const task_name = resolve_task_scan_task_name();
	if (task_name !== frappe.task_scan_page.task_name) {
		frappe.task_scan_page.task_name = task_name;
	}
	frappe.task_scan_page.load();
};

frappe.pages["task-scan"].on_page_hide = function () {
	if (frappe.task_scan_page) {
		frappe.task_scan_page.teardown_realtime();
	}
};

class TaskScanPage {
	constructor(page) {
		this.page = page;
		this.active_filter = "all";
		this.label_page = 1;
		this.selected_label_ids = new Set();
		this.task_name = resolve_task_scan_task_name();
		this._realtime_task = null;
		this.timer_state = null;
		this._on_task_scan_update = (data) => {
			if (!data || data.task !== this.task_name) {
				return;
			}
			const scanned_by = data.scanned_by;
			this.data = { ...this.data, ...data };
			this.render();
			if (data.ok && scanned_by && scanned_by !== frappe.session.user) {
				const label = data.item_instance_code ? ` (${data.item_instance_code})` : "";
				frappe.show_alert({
					message: __("Label scanned by {0}{1}", [scanned_by, label]),
					indicator: "blue",
				});
			}
		};
		this.$wrapper = $(frappe.render_template("task_scan")).appendTo(this.page.main);
		this.$wrapper.find(".task-scan-print-banner").remove();
		this.$hidden_scan = $('<input type="text" class="task-scan-hidden-scan-input" autocomplete="off">');
		this.$hidden_scan.appendTo(this.$wrapper);
		this.bind_events();
		this.load();
	}

	setup_realtime() {
		if (!this.task_name) {
			this.teardown_realtime();
			return;
		}
		if (this._realtime_task === this.task_name) {
			return;
		}
		this.teardown_realtime();
		frappe.realtime.on("task_scan_update", this._on_task_scan_update);
		frappe.realtime.doc_subscribe("Task", this.task_name);
		this._realtime_task = this.task_name;
	}

	teardown_realtime() {
		if (!this._realtime_task) {
			return;
		}
		frappe.realtime.off("task_scan_update", this._on_task_scan_update);
		frappe.realtime.doc_unsubscribe("Task", this._realtime_task);
		this._realtime_task = null;
	}

	load() {
		if (!this.task_name) {
			this.teardown_realtime();
			this.data = this.get_fallback_data();
			this.render();
			return;
		}

		this.setup_realtime();

		frappe.call({
			method: "fitzgerald_kitchens.fitzgerald_kitchens.page.task_scan.task_scan.get_task_scan_context",
			args: { task: this.task_name },
			freeze: true,
			callback: (r) => {
				this.data = r.message || this.get_fallback_data();
				if (this.data.task) {
					this.task_name = this.data.task;
					sessionStorage.setItem(TASK_SCAN_TASK_STORAGE_KEY, this.data.task);
				}
				this.load_timer_state();
			},
			error: () => {
				this.data = this.get_fallback_data();
				this.render();
			},
		});
	}

	load_timer_state() {
		if (!this.task_name) {
			this.timer_state = null;
			this.render();
			return;
		}

		frappe.call({
			method: "fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.task_timer.get_task_timer_state",
			args: { task: this.task_name },
			callback: (r) => {
				this.timer_state = r.message || null;
				this.render();
			},
			error: () => {
				this.timer_state = null;
				this.render();
			},
		});
	}

	call_timer_action(method) {
		if (!this.task_name) {
			return;
		}

		frappe.call({
			method: `fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.task_timer.${method}`,
			args: { task: this.task_name },
			freeze: true,
			callback: (r) => {
				if (!r.message) {
					return;
				}
				this.timer_state = r.message;
				this.render_timer_panel();
				if (method === "stop_task_timer") {
					frappe.show_alert({ message: __("Timer stopped"), indicator: "green" });
				}
			},
		});
	}

	render_timer_panel() {
		const timer = this.timer_state || {};
		const running = !!timer.timer_running;
		const paused = !!timer.timer_paused;
		const completed = this.data?.status === "Completed";
		const $status = this.$wrapper.find(".task-scan-timer-status");
		const $actions = this.$wrapper.find(".task-scan-timer-actions").empty();

		if (completed) {
			$status.text(__("Task completed"));
			return;
		}

		if (running) {
			$status.addClass("is-running").text(__("Timer running"));
			$actions.append(
				`<button type="button" class="btn btn-warning btn-sm btn-task-scan-pause">${__("Pause")}</button>`
			);
			$actions.append(
				`<button type="button" class="btn btn-danger btn-sm btn-task-scan-stop">${__("Stop")}</button>`
			);
		} else if (paused) {
			$status.removeClass("is-running").text(__("Timer paused"));
			$actions.append(
				`<button type="button" class="btn btn-primary btn-sm btn-task-scan-resume">${__("Resume")}</button>`
			);
			$actions.append(
				`<button type="button" class="btn btn-danger btn-sm btn-task-scan-stop">${__("Stop")}</button>`
			);
		} else {
			$status.removeClass("is-running").text(__("Timer not started"));
			$actions.append(
				`<button type="button" class="btn btn-primary btn-sm btn-task-scan-start">${__("Start task")}</button>`
			);
		}
	}

	get_fallback_data() {
		return {
			title: this.task_name || __("Task"),
			subtitle: "",
			task_type: __("Task"),
			due_label: "—",
			due_badge: __("No due date"),
			due_class: "",
			started_label: "—",
			assigned_to: __("Unassigned"),
			total_labels: 0,
			scanned: 0,
			outstanding: 0,
			errors: 0,
			printed: 0,
			labels: [],
		};
	}

	render() {
		const d = this.data;
		if (d.subtitle && this.page) {
			this.page.set_title(d.subtitle);
		} else if (d.title && this.page) {
			this.page.set_title(d.title);
		}
		const total = flt(d.total_labels) || 0;
		const pct = total ? Math.round((flt(d.scanned) / total) * 100) : 0;
		const remaining = Math.max(0, total - flt(d.scanned));

		this.$wrapper.find(".task-scan-title").text(d.title || "");
		this.$wrapper.find(".task-scan-subtitle").text(d.subtitle || "");
		this.$wrapper
			.find(".task-scan-due-badge")
			.text(d.due_badge ? `● ${d.due_badge}` : "")
			.toggleClass("is-overdue", d.due_class === "overdue")
			.toggleClass("due-today", d.due_class === "due-today");
		this.$wrapper.find(".task-scan-meta-type").text(d.task_type || __("Task"));
		this.$wrapper.find(".task-scan-meta-due").text(d.due_label || "—");
		this.$wrapper.find(".task-scan-meta-started").text(d.started_label || "—");
		this.$wrapper.find(".task-scan-meta-assigned").text(d.assigned_to || __("Unassigned"));

		this.render_timer_panel();

		this.$wrapper
			.find(".task-scan-scan-remaining")
			.text(
				total
					? __("{0} labels remaining to complete this task", [remaining])
					: __("No labels configured yet")
			);
		this.$wrapper
			.find(".task-scan-print-summary")
			.text(total ? __("{0} of {1} labels printed", [flt(d.printed), total]) : "");
		this.$wrapper
			.find(".task-scan-progress-count")
			.text(total ? __("{0} / {1} labels scanned", [d.scanned, total]) : __("No labels"));
		this.$wrapper.find(".task-scan-progress-pct").text(total ? __("{0}% complete", [pct]) : "");

		if (total) {
			const scanned_pct = (flt(d.scanned) / total) * 100;
			const error_pct = (flt(d.errors) / total) * 100;
			const outstanding_pct = (flt(d.outstanding) / total) * 100;
			this.$wrapper.find(".task-scan-bar-scanned").css("width", `${scanned_pct}%`);
			this.$wrapper.find(".task-scan-bar-errors").css("width", `${error_pct}%`);
			this.$wrapper.find(".task-scan-bar-outstanding").css("width", `${outstanding_pct}%`);
		}
		this.$wrapper.find(".task-scan-progress-bar").attr("aria-valuenow", pct);

		this.$wrapper.find(".task-scan-stat-num-printed").text(d.printed ?? 0);
		this.$wrapper.find(".task-scan-stat-num-scanned").text(d.scanned ?? 0);
		this.$wrapper.find(".task-scan-stat-num-outstanding").text(d.outstanding ?? 0);
		this.$wrapper.find(".task-scan-stat-num-errors").text(d.errors ?? 0);

		this.$wrapper.find('.task-scan-filter[data-filter="all"]').text(__("All {0}", [total]));
		this.$wrapper
			.find('.task-scan-filter[data-filter="outstanding"]')
			.text(__("Outstanding {0}", [d.outstanding ?? 0]));
		this.$wrapper
			.find('.task-scan-filter[data-filter="scanned"]')
			.text(__("Scanned {0}", [d.scanned ?? 0]));
		this.$wrapper
			.find('.task-scan-filter[data-filter="errors"]')
			.text(__("Errors {0}", [d.errors ?? 0]));

		this.render_label_list();
	}

	get_filtered_labels() {
		const labels = this.data?.labels || [];
		const filter = this.active_filter;
		if (filter === "errors") {
			return [];
		}
		if (filter === "all") {
			return labels;
		}
		return labels.filter((label) => label.status === filter);
	}

	render_label_list() {
		const status_labels = {
			scanned: __("Scanned"),
			outstanding: __("Outstanding"),
		};
		const $list = this.$wrapper.find(".task-scan-label-list");
		const $pagination = this.$wrapper.find(".task-scan-pagination");

		if (!(this.data?.labels || []).length) {
			$list.html(`<div class="text-muted small">${__("No QR labels for this project yet")}</div>`);
			$pagination.empty();
			return;
		}

		if (this.active_filter === "errors") {
			$list.html(
				`<div class="task-scan-errors-hint text-muted small">${__(
					"Invalid QR scans are counted above but are not listed because they do not match a project label."
				)}</div>`
			);
			$pagination.empty();
			return;
		}

		const filtered = this.get_filtered_labels();
		if (!filtered.length) {
			$list.html(
				`<div class="task-scan-errors-hint text-muted small">${__("No labels in this filter")}</div>`
			);
			$pagination.empty();
			return;
		}

		const total_pages = Math.max(1, Math.ceil(filtered.length / TASK_SCAN_PAGE_SIZE));
		this.label_page = Math.min(Math.max(this.label_page, 1), total_pages);
		const start = (this.label_page - 1) * TASK_SCAN_PAGE_SIZE;
		const page_items = filtered.slice(start, start + TASK_SCAN_PAGE_SIZE);

		const me = this;
		const rows = page_items
			.map((label) => {
				const subtitle = label.item_name
					? `<span class="task-scan-label-sub text-muted">${frappe.utils.escape_html(label.item_name)}</span>`
					: "";
				const selected = me.selected_label_ids.has(label.id);
				return `
			<div class="task-scan-label-row ${selected ? "is-selected" : ""}"
				data-label-id="${frappe.utils.escape_html(label.id)}"
				data-status="${frappe.utils.escape_html(label.status)}"
				role="button"
				tabindex="0"
				aria-pressed="${selected ? "true" : "false"}">
				<div class="task-scan-label-main">
					<span class="task-scan-label-id">${frappe.utils.escape_html(label.id)}</span>
					${subtitle}
				</div>
				<span class="task-scan-label-status ${frappe.utils.escape_html(label.status)}">
					${frappe.utils.escape_html(status_labels[label.status] || label.status)}
				</span>
			</div>`;
			})
			.join("");
		$list.html(rows);

		const end = Math.min(start + page_items.length, filtered.length);
		const range_label = __("Showing {0}–{1} of {2}", [start + 1, end, filtered.length]);

		$pagination.html(`
			<div class="task-scan-pagination-meta text-muted small">${frappe.utils.escape_html(range_label)}</div>
			<div class="task-scan-pagination-actions">
				<button type="button" class="btn btn-default btn-sm btn-task-scan-page-prev" ${
					this.label_page <= 1 ? "disabled" : ""
				}>${__("Previous")}</button>
				<span class="task-scan-pagination-page">${__(
					"Page {0} of {1}",
					[this.label_page, total_pages]
				)}</span>
				<button type="button" class="btn btn-default btn-sm btn-task-scan-page-next" ${
					this.label_page >= total_pages ? "disabled" : ""
				}>${__("Next")}</button>
			</div>
		`);
	}

	bind_events() {
		const me = this;

		this.$wrapper.find(".task-scan-filter").on("click", function () {
			me.$wrapper.find(".task-scan-filter").removeClass("active");
			$(this).addClass("active");
			me.active_filter = $(this).data("filter");
			me.label_page = 1;
			me.render_label_list();
		});

		this.$wrapper.on("click", ".btn-task-scan-page-prev", () => {
			if (me.label_page > 1) {
				me.label_page -= 1;
				me.render_label_list();
			}
		});

		this.$wrapper.on("click", ".btn-task-scan-page-next", () => {
			const filtered = me.get_filtered_labels();
			const total_pages = Math.max(1, Math.ceil(filtered.length / TASK_SCAN_PAGE_SIZE));
			if (me.label_page < total_pages) {
				me.label_page += 1;
				me.render_label_list();
			}
		});

		this.$wrapper.find(".btn-task-scan-primary").on("click", () => this.open_scanner());

		this.$wrapper.on("click", ".btn-task-scan-start", () => this.call_timer_action("start_task_timer"));
		this.$wrapper.on("click", ".btn-task-scan-resume", () => this.call_timer_action("resume_task_timer"));
		this.$wrapper.on("click", ".btn-task-scan-pause", () => this.call_timer_action("pause_task_timer"));
		this.$wrapper.on("click", ".btn-task-scan-stop", () => this.call_timer_action("stop_task_timer"));

		this.$hidden_scan.on("keydown", (e) => {
			if (e.key !== "Enter") {
				return;
			}
			const value = (me.$hidden_scan.val() || "").trim();
			me.$hidden_scan.val("");
			if (value) {
				me.handle_scan(value);
			}
		});

		$(document).on("keydown.task_scan_scan", (e) => {
			if ($(".modal:visible").length) {
				return;
			}
			if (
				$(e.target).is("input, textarea, select") &&
				!$(e.target).hasClass("task-scan-hidden-scan-input")
			) {
				return;
			}
			if (!me.$wrapper.is(":visible")) {
				return;
			}
			me.$hidden_scan.focus();
		});

		this.$wrapper.find(".btn-task-scan-print").on("click", () => this.download_all_qr_labels());
		this.$wrapper.find(".btn-task-scan-print-selected").on("click", () =>
			this.download_selected_qr_labels()
		);

		this.$wrapper.on("click", ".task-scan-label-row", function () {
			me.toggle_label_selection($(this).data("label-id"));
		});

		this.$wrapper.on("keydown", ".task-scan-label-row", function (e) {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				me.toggle_label_selection($(this).data("label-id"));
			}
		});
	}

	toggle_label_selection(label_id) {
		if (!label_id) {
			return;
		}
		if (this.selected_label_ids.has(label_id)) {
			this.selected_label_ids.delete(label_id);
		} else {
			this.selected_label_ids.add(label_id);
		}
		this.render_label_list();
	}

	download_single_qr_png(item_instance_code, qr_base64) {
		const link = document.createElement("a");
		link.href = `data:image/png;base64,${qr_base64}`;
		link.download = `${item_instance_code}.png`;
		document.body.appendChild(link);
		link.click();
		link.remove();
	}

	download_qr_labels_for_codes(codes, zip_filename) {
		const project = this.data?.project;
		if (!project) {
			frappe.msgprint(__("This task has no project linked."));
			return;
		}
		if (!codes.length) {
			frappe.msgprint(__("No QR labels to download."));
			return;
		}

		if (codes.length === 1) {
			frappe.call({
				method: "fitzgerald_kitchens.setup.project_qr_labels.get_qr_label_png_base64",
				args: { project, item_instance_code: codes[0] },
				freeze: true,
				callback: (r) => {
					const msg = r.message;
					if (!msg?.qr_base64) {
						frappe.msgprint(__("QR image is not available for this label."));
						return;
					}
					this.download_single_qr_png(msg.item_instance_code, msg.qr_base64);
				},
			});
			return;
		}

		const url =
			frappe.urllib.get_full_url(
				"/api/method/fitzgerald_kitchens.setup.project_qr_labels.download_selected_qr_zip"
			) +
			"?project=" +
			encodeURIComponent(project) +
			"&item_instance_codes=" +
			encodeURIComponent(JSON.stringify(codes));

		frappe.run_serially([
			() => frappe.dom.freeze(__("Preparing QR download...")),
			() =>
				fetch(url, { credentials: "include" }).then((response) => {
					if (!response.ok) {
						throw new Error(__("Could not download QR labels"));
					}
					return response.blob();
				}),
			(blob) => {
				const object_url = window.URL.createObjectURL(blob);
				const link = document.createElement("a");
				link.href = object_url;
				link.download = zip_filename;
				document.body.appendChild(link);
				link.click();
				link.remove();
				window.URL.revokeObjectURL(object_url);
			},
		])
			.catch(() => {
				frappe.msgprint(__("Could not download QR labels"));
			})
			.finally(() => {
				frappe.dom.unfreeze();
			});
	}

	download_all_qr_labels() {
		const project = this.data?.project;
		const codes = (this.data?.labels || []).map((label) => label.id).filter(Boolean);

		if (!project) {
			frappe.msgprint(__("This task has no project linked."));
			return;
		}
		if (!codes.length) {
			frappe.msgprint(__("No QR labels for this task yet."));
			return;
		}

		this.download_qr_labels_for_codes(codes, `${project}-qr-labels.zip`);
	}

	download_selected_qr_labels() {
		const selected = Array.from(this.selected_label_ids);

		if (!selected.length) {
			frappe.msgprint(__("Select one or more labels from the list first."));
			return;
		}

		const project = this.data?.project || "labels";
		this.download_qr_labels_for_codes(selected, `${project}-qr-selected.zip`);
	}

	open_scanner() {
		const me = this;
		const scanner = new frappe.ui.Scanner({
			dialog: true,
			multiple: false,
			on_scan(result) {
				const qr_text = result?.decodedText || result;
				if (qr_text) {
					me.handle_scan(qr_text);
				}
			},
		});
		scanner.scan();
	}

	handle_scan(qr_text) {
		if (!this.task_name) {
			frappe.msgprint(__("Open this page from a task to scan labels."));
			return;
		}

		frappe.call({
			method: "fitzgerald_kitchens.fitzgerald_kitchens.page.task_scan.task_scan.scan_task_label",
			args: { task: this.task_name, qr_text },
			freeze: true,
			callback: (r) => {
				const msg = r.message;
				if (!msg) {
					return;
				}
				this.data = { ...this.data, ...msg };
				if (msg.timer) {
					this.timer_state = msg.timer;
				}
				this.render();
				if (msg.task_completed) {
					const mrSubmit = msg.material_request_submit || {};
					const mr =
						mrSubmit.new_mr ||
						mrSubmit.submitted_existing_mr ||
						mrSubmit.name ||
						msg.material_request;
					const mrWarnings = [
						...(msg.material_request_warnings || []),
						...(mrSubmit.errors || []),
					].filter(Boolean);
					const mrError = msg.material_request_error || mrWarnings.join("; ");
					const mrSkipped = msg.material_request_skipped;
					const stockEntry = (mrSubmit.stock_entries || [])[0];
					let completeMessage = stockEntry
						? __("All labels scanned — task completed, MR {0} submitted and Stock Entry {1} issued", [
								mr,
								stockEntry,
							])
						: mr
							? __("All labels scanned — task completed and Material Request {0} submitted", [mr])
							: __("All labels scanned — timer stopped, timesheet submitted, task completed");
					if (mrError) {
						completeMessage = __("Task completed but material issue failed: {0}", [mrError]);
						frappe.msgprint({
							title: __("Material Issue Error"),
							message: mrError,
							indicator: "orange",
						});
					} else if (mrSkipped) {
						completeMessage = __("Task completed (Material Request skipped: {0})", [mrSkipped]);
					}
					frappe.show_alert({
						message: completeMessage,
						indicator: mrError ? "orange" : "green",
					});
				} else if (msg.ok) {
					frappe.show_alert({
						message: msg.timer_started
							? __("Label scanned — timer started")
							: msg.message || __("Label scanned"),
						indicator: "green",
					});
				} else {
					frappe.show_alert({
						message: msg.message || __("Scan failed"),
						indicator:
							msg.result === "duplicate" || msg.result === "other_task" ? "orange" : "red",
					});
				}
			},
		});
	}
}
