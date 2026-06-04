// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.pages["task-scan"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Task Scan"),
		single_column: true,
		hide_sidebar: true,
	});

	frappe.task_scan_page = new TaskScanPage(page);
};

class TaskScanPage {
	constructor(page) {
		this.page = page;
		this.active_filter = "all";
		this.task_name =
			frappe.route_options?.task || frappe.utils.get_query_params()?.task || "";
		this.$wrapper = $(frappe.render_template("task_scan")).appendTo(this.page.main);
		this.bind_events();
		this.load();
	}

	load() {
		if (!this.task_name) {
			this.data = this.get_fallback_data();
			this.render();
			return;
		}

		frappe.call({
			method: "fitzgerald_kitchens.fitzgerald_kitchens.page.task_scan.task_scan.get_task_scan_context",
			args: { task: this.task_name },
			freeze: true,
			callback: (r) => {
				this.data = r.message || this.get_fallback_data();
				this.render();
			},
			error: () => {
				this.data = this.get_fallback_data();
				this.render();
			},
		});
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
			print_banner: "",
			labels: [],
		};
	}

	render() {
		const d = this.data;
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
		this.$wrapper.find(".task-scan-banner-text").text(d.print_banner || "");

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

	render_label_list() {
		const d = this.data;
		const labels = d.labels || [];
		const status_labels = {
			scanned: __("Scanned"),
			outstanding: __("Outstanding"),
			error: __("Error"),
		};
		if (!labels.length) {
			this.$wrapper
				.find(".task-scan-label-list")
				.html(`<div class="text-muted small">${__("No labels yet")}</div>`);
			return;
		}
		const rows = labels
			.map(
				(label) => `
			<div class="task-scan-label-row" data-status="${frappe.utils.escape_html(label.status)}">
				<span class="task-scan-label-id">${frappe.utils.escape_html(label.id)}</span>
				<span class="task-scan-label-status ${frappe.utils.escape_html(label.status)}">
					${frappe.utils.escape_html(status_labels[label.status] || label.status)}
				</span>
			</div>`
			)
			.join("");
		this.$wrapper.find(".task-scan-label-list").html(rows);
		this.apply_filter();
	}

	apply_filter() {
		const filter = this.active_filter;
		this.$wrapper.find(".task-scan-label-row").each(function () {
			const status = $(this).data("status");
			const show = filter === "all" || status === filter;
			$(this).toggleClass("is-hidden", !show);
		});
	}

	bind_events() {
		const me = this;

		this.$wrapper.find(".task-scan-filter").on("click", function () {
			me.$wrapper.find(".task-scan-filter").removeClass("active");
			$(this).addClass("active");
			me.active_filter = $(this).data("filter");
			me.apply_filter();
		});

		this.$wrapper.find(".btn-task-scan-primary").on("click", () => {
			frappe.show_alert({ message: __("Scanner will be connected here"), indicator: "blue" });
		});

		this.$wrapper.find(".btn-task-scan-print, .btn-task-scan-reprint, .btn-task-scan-print-selected").on(
			"click",
			() => {
				frappe.show_alert({ message: __("Print will be connected here"), indicator: "blue" });
			}
		);
	}
}
