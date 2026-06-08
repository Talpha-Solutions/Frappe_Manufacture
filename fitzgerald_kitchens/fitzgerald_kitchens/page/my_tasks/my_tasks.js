// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.pages["my-tasks"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("My Tasks"),
		single_column: true,
	});

	frappe.my_tasks_page = new MyTasksPage(page);
};

frappe.pages["my-tasks"].on_page_show = function () {
	if (frappe.my_tasks_page) {
		frappe.my_tasks_page.refresh();
	}
};

frappe.pages["my-tasks"].on_page_hide = function () {
	if (frappe.my_tasks_page) {
		frappe.my_tasks_page.clear_timer_interval();
	}
};

const COLLAPSE_STORAGE_KEY = "my_tasks_card_sections";
const LABEL_SCAN_TASK_TYPES = new Set(["Assembly", "Despatch", "Dispatch", "Delivery"]);

function is_label_scan_task_type(task_type) {
	if (!task_type) {
		return false;
	}
	const normalized = String(task_type).trim().toLowerCase();
	if (normalized === "dispatch") {
		return true;
	}
	return LABEL_SCAN_TASK_TYPES.has(task_type);
}

class MyTasksPage {
	constructor(page) {
		this.page = page;
		this.active_tab = "today";
		this.data = null;
		this.scanner_task = null;
		this._timer_interval = null;
		this.$wrapper = $(frappe.render_template("my_tasks")).appendTo(this.page.main);
		// Legacy timer epoch cache caused stale 4h+ stopwatch displays.
		localStorage.removeItem("my_tasks_timer_epochs");
		this.bind_events();
		this.refresh();
	}

	get_collapse_state() {
		try {
			return JSON.parse(localStorage.getItem(COLLAPSE_STORAGE_KEY) || "{}");
		} catch {
			return {};
		}
	}

	is_section_collapsed(task_name, section, default_collapsed = false) {
		const key = `${task_name}:${section}`;
		const state = this.get_collapse_state();
		if (Object.prototype.hasOwnProperty.call(state, key)) {
			return !!state[key];
		}
		return default_collapsed;
	}

	set_section_collapsed(task_name, section, collapsed) {
		const state = this.get_collapse_state();
		state[`${task_name}:${section}`] = collapsed;
		localStorage.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify(state));
	}

	elapsed_seconds_from_server_base(serverElapsed, renderedAt) {
		const base = flt(serverElapsed) || 0;
		const since = renderedAt ? Math.floor((Date.now() - renderedAt) / 1000) : 0;
		return Math.max(0, base + since);
	}

	render_collapsible_section(task_name, section, title, body_html, subtitle = "", default_collapsed = false) {
		const collapsed = this.is_section_collapsed(task_name, section, default_collapsed);
		const subtitle_html = subtitle
			? `<span class="my-tasks-collapse-sub">${frappe.utils.escape_html(subtitle)}</span>`
			: "";
		return `<div class="my-tasks-collapse ${collapsed ? "is-collapsed" : ""}" data-section="${frappe.utils.escape_html(section)}">
			<button type="button" class="my-tasks-collapse-header" aria-expanded="${collapsed ? "false" : "true"}">
				<span class="my-tasks-collapse-chevron" aria-hidden="true"></span>
				<span class="my-tasks-collapse-title">${frappe.utils.escape_html(title)}</span>
				${subtitle_html}
			</button>
			<div class="my-tasks-collapse-body">${body_html}</div>
		</div>`;
	}

	bind_collapse_handlers($card, task_name) {
		const me = this;
		$card.find(".my-tasks-collapse-header").on("click", function (e) {
			e.preventDefault();
			const $section = $(this).closest(".my-tasks-collapse");
			const section = $section.data("section");
			const collapsed = !$section.hasClass("is-collapsed");
			$section.toggleClass("is-collapsed", collapsed);
			$(this).attr("aria-expanded", collapsed ? "false" : "true");
			const $title = $(this).find(".my-tasks-collapse-title");
			$title.text(collapsed ? __("Show details") : __("Hide details"));
			me.set_section_collapsed(task_name, section, collapsed);
			if (!collapsed) {
				me.start_timer_interval();
			}
		});
	}

	bind_events() {
		this.$wrapper.find(".btn-open-scanner").on("click", () => this.open_scanner());

		this.$hidden_scan = $('<input type="text" class="my-tasks-hidden-scan-input" autocomplete="off">');
		this.$hidden_scan.appendTo(this.$wrapper);
		this.$hidden_scan.on("keydown", (e) => {
			if (e.key !== "Enter") {
				return;
			}
			const value = (this.$hidden_scan.val() || "").trim();
			this.$hidden_scan.val("");
			if (!value) {
				return;
			}
			this.handle_scan(value);
		});

		$(document).on("keydown.my_tasks_scan", (e) => {
			if ($(".modal:visible").length) {
				return;
			}
			if ($(e.target).is("input, textarea, select") && !$(e.target).hasClass("my-tasks-hidden-scan-input")) {
				return;
			}
			if (!this.$wrapper.is(":visible")) {
				return;
			}
			this.$hidden_scan.focus();
		});
	}

	refresh() {
		frappe.call({
			method: "fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.my_tasks.get_my_tasks_dashboard",
			freeze: true,
			callback: (r) => {
				if (!r.message) {
					return;
				}
				this.data = r.message;
				this.render();
			},
			error: () => {
				frappe.msgprint({
					title: __("Not permitted"),
					message: __("You do not have access to My Tasks."),
					indicator: "red",
				});
			},
		});
	}

	render() {
		const d = this.data;
		this.render_header(d.user);
		this.render_kpis(d.kpis);
		this.render_tabs(d.tabs);
		this.render_tasks(d.tabs[this.active_tab]?.tasks || []);
		this.start_timer_interval();
	}

	clear_timer_interval() {
		if (this._timer_interval) {
			clearInterval(this._timer_interval);
			this._timer_interval = null;
		}
	}

	start_timer_interval() {
		this.clear_timer_interval();
		if (!this.$wrapper.find(".my-tasks-timer-display[data-server-elapsed]").length) {
			return;
		}
		this.update_running_timers();
		this._timer_interval = setInterval(() => this.update_running_timers(), 1000);
	}

	update_running_timers() {
		const me = this;
		this.$wrapper.find(".my-tasks-timer-display[data-server-elapsed]").each(function () {
			const $el = $(this);
			const serverElapsed = flt($el.attr("data-server-elapsed"));
			const renderedAt = parseInt($el.attr("data-rendered-at"), 10) || Date.now();
			const expectedHours = flt($el.attr("data-expected-hours"));
			const elapsed = me.elapsed_seconds_from_server_base(serverElapsed, renderedAt);
			$el.find(".timer-elapsed").text(MyTasksPage.format_duration(elapsed));
			const $remaining = $el.find(".timer-remaining");
			if (expectedHours > 0) {
				const remaining = Math.floor(expectedHours * 3600 - elapsed);
				$remaining
					.text(MyTasksPage.format_duration(Math.abs(remaining), true))
					.toggleClass("text-danger", remaining < 0)
					.toggleClass("text-muted", remaining >= 0)
					.show();
				$el.find(".timer-remaining-label").text(remaining < 0 ? __("Over by") : __("Remaining")).show();
			} else {
				$remaining.hide();
				$el.find(".timer-remaining-label").hide();
			}
		});
	}

	static format_duration(totalSeconds, allow_hours_over_99 = false) {
		const sign = totalSeconds < 0 ? "-" : "";
		const seconds = Math.abs(totalSeconds);
		const hours = Math.floor(seconds / 3600);
		const minutes = Math.floor((seconds % 3600) / 60);
		const secs = seconds % 60;
		if (allow_hours_over_99 || hours <= 99) {
			return `${sign}${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
		}
		return `${sign}${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
	}

	render_timesheet_logs_body(task) {
		const logs = task.timesheet_logs || [];
		const rows = logs
			.map((log) => {
				const from = log.from_time ? frappe.datetime.str_to_user(log.from_time) : "—";
				const to = log.to_time ? frappe.datetime.str_to_user(log.to_time) : __("Running");
				const hours = log.hours ? `${flt(log.hours).toFixed(2)}h` : "—";
				return `<div class="my-tasks-ts-row">
					<span class="my-tasks-ts-range">${frappe.utils.escape_html(from)} → ${frappe.utils.escape_html(to)}</span>
					<span class="my-tasks-ts-meta">${frappe.utils.escape_html(hours)} · ${frappe.utils.escape_html(log.status_label || "")}</span>
				</div>`;
			})
			.join("");
		const total = flt(task.total_logged_hours)
			? `<div class="my-tasks-ts-total text-muted small">${__("Logged")}: ${flt(task.total_logged_hours).toFixed(2)}h</div>`
			: "";
		return `${rows || `<div class="text-muted small">${__("No entries yet")}</div>`}${total}`;
	}

	render_timesheet_section(task) {
		const logs = task.timesheet_logs || [];
		if (!logs.length && !flt(task.total_logged_hours)) {
			return "";
		}
		return `<div class="my-tasks-timesheet-block">
			<div class="my-tasks-timesheet-title">${__("Timesheet")}</div>
			${this.render_timesheet_logs_body(task)}
		</div>`;
	}

	get_card_details_subtitle(task) {
		const parts = [];
		const progress = Math.round(flt(task.progress));
		if (progress > 0) {
			parts.push(`${progress}%`);
		}
		if (task.timer_running) {
			parts.push(__("Timer running"));
		} else if (flt(task.total_logged_hours)) {
			parts.push(`${flt(task.total_logged_hours).toFixed(2)}h`);
		}
		return parts.length ? parts.join(" · ") : __("Tap to show");
	}

	render_task_controls_body(task) {
		if (task.status === "Completed" || task.status === "Cancelled" || task.status === "Template") {
			return "";
		}
		const progress = Math.round(flt(task.progress));
		const timer_active = !!task.timer_running || !!task.timer_paused;
		const complete_disabled = timer_active ? "disabled" : "";
		const complete_title = timer_active
			? frappe.utils.escape_html(__("Stop the timer before completing"))
			: "";

		return `<div class="my-tasks-task-controls">
			<div class="my-tasks-control-row">
				<label class="my-tasks-control-label">${__("Progress")}</label>
				<input type="number" class="form-control input-sm my-tasks-progress-input" min="0" max="100" value="${progress}">
				<span class="my-tasks-progress-suffix">%</span>
				<button type="button" class="btn btn-default btn-sm btn-task-progress-update">${__("Update")}</button>
			</div>
			<button type="button" class="btn btn-success btn-sm btn-task-complete" ${complete_disabled} title="${complete_title}">${__("Complete")}</button>
		</div>`;
	}

	render_card_details_panel(task, body_html) {
		const collapsed_label = __("Show details");
		const expanded_label = __("Hide details");
		const collapsed = this.is_section_collapsed(task.name, "details", true);
		const title = collapsed ? collapsed_label : expanded_label;
		return this.render_collapsible_section(
			task.name,
			"details",
			title,
			`<div class="my-tasks-card-details-inner">${body_html}</div>`,
			this.get_card_details_subtitle(task),
			true
		);
	}

	render_timer_block(task) {
		const running = task.timer_running;
		const paused = task.timer_paused;
		const expected = flt(task.timer_expected_hours);
		const serverElapsed = running ? flt(task.timer_elapsed_seconds) || 0 : 0;
		const renderedAt = Date.now();
		const initialElapsed = running ? this.elapsed_seconds_from_server_base(serverElapsed, renderedAt) : 0;
		const timerHtml = running
			? `<div class="my-tasks-timer-display"
					data-server-elapsed="${serverElapsed}"
					data-rendered-at="${renderedAt}"
					data-expected-hours="${expected || 0}">
					<div class="my-tasks-timer-label text-muted small">${__("Elapsed")}</div>
					<span class="timer-elapsed">${MyTasksPage.format_duration(initialElapsed)}</span>
					${
						expected
							? `<span class="timer-sep"> · </span><span class="timer-remaining-label">${__("Remaining")}</span> <span class="timer-remaining">--:--:--</span>`
							: ""
					}
				</div>`
			: "";

		let actionButtons = "";
		if (task.status !== "Completed") {
			if (running) {
				actionButtons = `
					<button type="button" class="btn btn-warning btn-sm btn-task-pause">${__("Pause")}</button>
					<button type="button" class="btn btn-danger btn-sm btn-task-stop">${__("Stop")}</button>
				`;
			} else if (paused) {
				actionButtons = `
					<button type="button" class="btn btn-primary btn-sm btn-task-resume">${__("Resume")}</button>
					<button type="button" class="btn btn-danger btn-sm btn-task-stop">${__("Stop")}</button>
				`;
			} else {
				actionButtons = `<button type="button" class="btn btn-primary btn-sm btn-task-start">${__("Start task")}</button>`;
			}
			if (is_label_scan_task_type(task.type)) {
				actionButtons += `<button type="button" class="btn btn-default btn-sm btn-task-scan">${__("Scan")}</button>`;
			}
		}
		actionButtons += `<button type="button" class="btn btn-default btn-sm btn-task-details">${__("Details")}</button>`;

		const inner = `${this.render_task_controls_body(task)}
			${timerHtml ? `<div class="my-tasks-timer-row">${timerHtml}</div>` : ""}
			<div class="my-tasks-card-actions my-tasks-timer-actions">${actionButtons}</div>
			${this.render_timesheet_section(task)}`;

		return this.render_card_details_panel(task, inner);
	}

	call_task_update(method, task, extra_args = {}) {
		frappe.call({
			method: `fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.task_timer.${method}`,
			args: { task: task.name, ...extra_args },
			freeze: true,
			callback: (r) => {
				if (!r.message) {
					return;
				}
				if (method === "complete_task") {
					let message = __("Task completed");
					if (r.message.timesheet_submit?.submitted) {
						message = __("Task completed and timesheet {0} submitted", [
							r.message.timesheet_submit.timesheet,
						]);
					}
					frappe.show_alert({
						message,
						indicator: "green",
					});
					if (this.active_tab !== "completed") {
						this.active_tab = "completed";
					}
				} else if (method === "update_task_progress") {
					const pct = Math.round(flt(r.message.task_update?.progress));
					frappe.show_alert({
						message: __("Progress updated to {0}%", [pct]),
						indicator: "green",
					});
				}
				this.refresh();
			},
		});
	}

	call_timer_action(method, task) {
		frappe.call({
			method: `fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.task_timer.${method}`,
			args: { task: task.name },
			freeze: true,
			callback: (r) => {
				if (!r.message) {
					return;
				}
				if (method === "stop_task_timer") {
					frappe.show_alert({
						message: __("Timer stopped"),
						indicator: "green",
					});
				}
				if (
					(method === "start_task_timer" || method === "resume_task_timer") &&
					r.message.auto_stopped_task?.stopped_task
				) {
					frappe.show_alert({
						message: __("Previous timer on {0} stopped and time saved", [
							r.message.auto_stopped_task.stopped_task,
						]),
						indicator: "blue",
					});
				}
				this.refresh();
			},
		});
	}

	render_header(user) {
		const $avatar = this.$wrapper.find(".my-tasks-avatar");
		if (user.user_image) {
			$avatar.html(`<img src="${frappe.utils.escape_html(user.user_image)}" alt="">`);
		} else {
			$avatar.text(user.abbr || "?");
		}
		this.$wrapper.find(".my-tasks-user-name").text(user.full_name);
		this.$wrapper.find(".my-tasks-user-dept").text(user.department || "");
		this.$wrapper.find(".my-tasks-date").text(user.date_label || "");
	}

	render_kpis(kpis) {
		this.$wrapper.find(".my-kpi-completed").text(kpis.completed_today ?? 0);
		this.$wrapper.find(".my-kpi-due").text(kpis.due_today ?? 0);
		this.$wrapper.find(".my-kpi-overdue").text(kpis.overdue ?? 0);
	}

	render_tabs(tabs) {
		const tab_defs = [
			{ key: "today", label: __("Today") },
			{ key: "overdue", label: __("Overdue") },
			{ key: "upcoming", label: __("Upcoming") },
			{ key: "completed", label: __("Completed") },
		];
		const $tabs = this.$wrapper.find(".my-tasks-tabs").empty();

		tab_defs.forEach((tab) => {
			const count = tabs[tab.key]?.count ?? 0;
			const $btn = $(`
				<button type="button" class="my-tasks-tab ${tab.key === this.active_tab ? "active" : ""}" data-tab="${tab.key}">
					${tab.label}<span class="tab-count">(${count})</span>
				</button>
			`);
			$btn.on("click", () => {
				this.active_tab = tab.key;
				this.render_tabs(tabs);
				this.render_tasks(tabs[tab.key]?.tasks || []);
				this.start_timer_interval();
			});
			$tabs.append($btn);
		});
	}

	render_tasks(tasks) {
		const me = this;
		const $list = this.$wrapper.find(".my-tasks-list").empty();
		const $empty = this.$wrapper.find(".my-tasks-empty");

		if (!tasks.length) {
			$empty.show();
			return;
		}
		$empty.hide();

		tasks.forEach((task) => {
			const due_class =
				task.due_label === __("Starts today") ||
				task.due_label === "Starts today" ||
				task.due_label === __("DUE Today") ||
				task.due_label === "DUE Today"
					? "due-today"
					: task.due_label === __("Overdue") || task.due_label === "Overdue"
						? "overdue"
						: "";
			const progress = flt(task.progress);
			const progress_label =
				progress > 0
					? `${Math.round(progress)}%`
					: task.image_count
						? __("{0} Images", [task.image_count])
						: task.timer_running
							? __("In progress")
							: flt(task.total_logged_hours)
								? __("{0}h logged", [flt(task.total_logged_hours).toFixed(1)])
								: __("Not started");
			const progress_class = progress > 0 || task.timer_running ? "" : "muted";

			const $card = $(`
				<div class="my-tasks-card" data-task="${frappe.utils.escape_html(task.name)}">
					<div class="my-tasks-card-top">
						<div>
							<div class="my-tasks-card-title">${frappe.utils.escape_html(task.project_label || task.unit_subtitle || task.project || "")}</div>
							<div class="my-tasks-card-sub">${frappe.utils.escape_html(task.subject)}</div>
						</div>
						${task.due_label ? `<div class="my-tasks-due ${due_class}">${frappe.utils.escape_html(task.due_label)}</div>` : ""}
					</div>
					<div class="my-tasks-card-meta">
						<span class="my-tasks-badge">${frappe.utils.escape_html(task.type || __("Task"))}</span>
						<span class="my-tasks-status-badge">${frappe.utils.escape_html(task.status || __("Open"))}</span>
						<span class="my-tasks-progress-badge ${progress_class}">${frappe.utils.escape_html(progress_label)}</span>
					</div>
					${this.render_timer_block(task)}
				</div>
			`);

			$card.find(".btn-task-details").on("click", () => {
				frappe.set_route("Form", "Task", task.name);
			});
			$card.find(".btn-task-start").on("click", () => this.call_timer_action("start_task_timer", task));
			$card.find(".btn-task-resume").on("click", () => this.call_timer_action("resume_task_timer", task));
			$card.find(".btn-task-pause").on("click", () => this.call_timer_action("pause_task_timer", task));
			$card.find(".btn-task-stop").on("click", () => this.call_timer_action("stop_task_timer", task));
			$card.find(".btn-task-scan").on("click", () => {
				sessionStorage.setItem("task_scan_task", task.name);
				frappe.route_options = { task: task.name };
				frappe.set_route("task-scan");
			});
			$card.find(".btn-task-progress-update").on("click", () => {
				const progress = flt($card.find(".my-tasks-progress-input").val());
				this.call_task_update("update_task_progress", task, { progress });
			});
			$card.find(".btn-task-complete").on("click", function () {
				if ($(this).prop("disabled")) {
					frappe.show_alert({
						message: __("Use Stop to end your session before completing this task."),
						indicator: "orange",
					});
					return;
				}
				frappe.confirm(
					__("Mark this task complete, submit the timesheet, and set progress to 100%?"),
					() => {
						me.call_task_update("complete_task", task);
					}
				);
			});
			me.bind_collapse_handlers($card, task.name);

			$list.append($card);
		});
	}

	open_scanner(task) {
		this.scanner_task = task || null;
		this.open_qr_camera_scanner();
	}

	open_qr_camera_scanner() {
		const me = this;
		const scanner = new frappe.ui.Scanner({
			dialog: true,
			multiple: false,
			on_scan(result) {
				const qr_text = result?.decodedText || result;
				if (qr_text) {
					me.scanner_task = null;
					me.handle_scan(qr_text);
				}
			},
		});
		scanner.scan();
	}

	handle_scan(qr_text) {
		frappe.call({
			method: "fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.my_tasks.open_qr_scan_from_code",
			args: { qr_text },
			freeze: true,
			callback: (r) => {
				const msg = r.message;
				if (!msg?.development_unit) {
					frappe.msgprint(__("Could not resolve QR code"));
					return;
				}
				frappe.new_doc("Development Unit QR Scan", {
					development_unit: msg.development_unit,
				});
			},
		});
	}
}
