// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const PAT_REPORT_NAME = "Project Actual Timeline";

const PAT_STATUS_COLORS = {
	Open: "#3498db",
	"In Progress": "#2980b9",
	Completed: "#27ae60",
	Cancelled: "#95a5a6",
	"On Hold": "#f39c12",
};

const PAT_SCHEDULE_COLORS = {
	Late: "#e74c3c",
	Early: "#27ae60",
	"On Time": "#2980b9",
};

const PAT_SCHEDULED_FILL = "#d5f5e3";
const PAT_SCHEDULED_COLOR = "#52be80";
const PAT_OVERDUE_COLOR = "#e74c3c";
const PAT_AXIS_DAY_STEP = 7;
const PAT_LABEL_MIN_GAP = 82;
const PAT_ROW_LAYOUT = {
	row_h: 96,
	scheduled_bar_y: 36,
	actual_bar_y: 62,
	bar_h: 11,
};

function pat_is_report(report) {
	if (report?.report_name) {
		return report.report_name === PAT_REPORT_NAME;
	}
	const route = frappe.get_route();
	if (route[0] === "query-report") {
		return route[1] === PAT_REPORT_NAME;
	}
	return frappe.query_report?.report_name === PAT_REPORT_NAME;
}

function pat_teardown() {
	$(".pat-dashboard").remove();
}

function pat_register_route_teardown() {
	if (window._pat_route_teardown_registered) {
		return;
	}
	window._pat_route_teardown_registered = true;

	frappe.router.on("change", () => {
		const route = frappe.get_route();
		if (route[0] !== "query-report" || route[1] !== PAT_REPORT_NAME) {
			pat_teardown();
		}
	});
}

pat_register_route_teardown();

frappe.query_reports[PAT_REPORT_NAME] = {
	filters: [
		{
			label: __("Company"),
			fieldname: "company",
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
			on_change(query_report) {
				query_report.set_filter_value("site_project", "");
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
			on_change(query_report) {
				const fiscal_year = query_report.get_values().fiscal_year;
				if (!fiscal_year) {
					return;
				}
				frappe.model.with_doc("Fiscal Year", fiscal_year, () => {
					const fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
					frappe.query_report.set_filter_value({
						from_date: fy.year_start_date,
						to_date: fy.year_end_date,
					});
				});
			},
		},
		{
			label: __("From Date"),
			fieldname: "from_date",
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
		},
		{
			label: __("To Date"),
			fieldname: "to_date",
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[2],
		},
		{
			label: __("Site Project"),
			fieldname: "site_project",
			fieldtype: "Link",
			options: "Project",
			get_query: () => {
				const company = frappe.query_report?.get_filter_value("company");
				return {
					query:
						"fitzgerald_kitchens.fitzgerald_kitchens.report.project_actual_timeline.project_actual_timeline.site_project_query",
					filters: { company },
				};
			},
		},
		{
			label: __("Status"),
			fieldname: "status",
			fieldtype: "Select",
			options: ["", "Open", "In Progress", "Completed", "Cancelled", "On Hold"],
		},
	],

	onload() {
		pat_inject_styles();
	},

	get_chart_data() {
		return null;
	},

	after_refresh() {
		if (!pat_is_report()) {
			return;
		}
		pat_render_dashboard();
	},

	after_datatable_render() {
		if (!pat_is_report()) {
			return;
		}
		pat_render_dashboard();
	},

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "schedule_status" && value) {
			const color = PAT_SCHEDULE_COLORS[value] || "#5a6773";
			const delay = cint(row.delay_days);
			const suffix =
				value === "Late" && delay > 0
					? ` <span style="color:${PAT_OVERDUE_COLOR};font-weight:700">(${__(
							"{0}d overdue",
							[delay]
					  )})</span>`
					: "";
			return `<span style="color:${color};font-weight:600">${frappe.utils.escape_html(
				value
			)}${suffix}</span>`;
		}
		if (column.fieldname === "delay_days" && value !== null && value !== undefined && value !== "") {
			const amount = cint(value);
			if (!amount) {
				return default_formatter(value, row, column, data);
			}
			if (amount > 0) {
				return `<div style="color:${PAT_OVERDUE_COLOR};font-weight:700;text-align:right">${__(
					"{0} days overdue",
					[amount]
				)}</div>`;
			}
			return `<div style="color:#27ae60;font-weight:600;text-align:right">${amount}</div>`;
		}
		return default_formatter(value, row, column, data);
	},
};

function pat_inject_styles() {
	if (document.getElementById("pat-report-styles")) {
		return;
	}

	const css = `
		.pat-dashboard { background: #fff; border: 1px solid #e8eaed; border-radius: 10px; padding: 18px 22px 22px; margin: 12px 0 16px; }
		.pat-header { margin-bottom: 14px; }
		.pat-title { font-size: 18px; font-weight: 700; color: #1f272e; margin: 0 0 6px; }
		.pat-context { font-size: 12px; color: #5a6773; line-height: 1.45; }
		.pat-context strong { color: #1f272e; }
		.pat-guide { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }
		@media (max-width: 900px) { .pat-guide { grid-template-columns: 1fr; } }
		.pat-guide-card { background: #f8fafc; border: 1px solid #eef0f3; border-radius: 8px; padding: 10px 12px; font-size: 11px; color: #5a6773; line-height: 1.45; }
		.pat-guide-card strong { display: block; color: #1f272e; font-size: 11px; margin-bottom: 4px; }
		.pat-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
		@media (max-width: 900px) { .pat-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
		.pat-kpi { border-radius: 8px; padding: 12px 14px; border: 1px solid rgba(0,0,0,0.04); }
		.pat-kpi--blue { background: #ebf5fb; }
		.pat-kpi--green { background: #eafaf1; }
		.pat-kpi--orange { background: #fef5e7; }
		.pat-kpi--red { background: #fdecea; }
		.pat-kpi-label { font-size: 10px; font-weight: 600; color: #6c7a89; text-transform: uppercase; letter-spacing: 0.03em; }
		.pat-kpi-value { font-size: 24px; font-weight: 800; color: #1f272e; margin-top: 4px; line-height: 1.1; }
		.pat-kpi-foot { font-size: 10px; color: #8d99a6; margin-top: 4px; }
		.pat-legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 11px; color: #5a6773; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #eef0f3; }
		.pat-legend-item { display: inline-flex; align-items: center; gap: 6px; }
		.pat-legend-swatch { width: 22px; height: 10px; border-radius: 3px; flex-shrink: 0; }
		.pat-legend-swatch--scheduled { background: ${PAT_SCHEDULED_FILL}; border: 2px dashed ${PAT_SCHEDULED_COLOR}; }
		.pat-legend-swatch--today { background: transparent; border: 2px dashed #e74c3c; width: 2px; height: 14px; border-radius: 0; }
		.pat-chart-panel { border: 1px solid #eef0f3; border-radius: 8px; background: #fafbfc; overflow: hidden; }
		.pat-chart-head { display: grid; grid-template-columns: 260px 1fr; background: #f4f6f8; border-bottom: 1px solid #e8eaed; font-size: 10px; font-weight: 700; color: #8d99a6; text-transform: uppercase; letter-spacing: 0.04em; }
		.pat-chart-head div { padding: 8px 12px; }
		.pat-chart-wrap { width: 100%; overflow-x: auto; position: relative; }
		.pat-chart-svg { display: block; min-width: 900px; }
		.pat-axis { stroke: #e8eaed; stroke-width: 1; }
		.pat-month-line { stroke: #f0f2f5; stroke-width: 1; }
		.pat-today-line { stroke: #e74c3c; stroke-width: 2; stroke-dasharray: 5 4; }
		.pat-today-label { fill: #e74c3c; font-size: 10px; font-weight: 700; }
		.pat-row-bg { fill: #fff; }
		.pat-row-bg--alt { fill: #fcfdfe; }
		.pat-row-divider { stroke: #f0f2f5; stroke-width: 1; }
		.pat-col-divider { stroke: #e8eaed; stroke-width: 1; }
		.pat-row-label { fill: #1f272e; font-size: 11px; font-weight: 700; }
		.pat-row-lane { fill: #8d99a6; font-size: 9px; font-weight: 600; dominant-baseline: middle; }
		.pat-lane-guide { stroke: #eef0f3; stroke-width: 1; }
		.pat-bar-scheduled { fill: ${PAT_SCHEDULED_FILL}; stroke: ${PAT_SCHEDULED_COLOR}; stroke-width: 1.5; stroke-dasharray: 6 4; cursor: pointer; }
		.pat-bar-actual { cursor: pointer; }
		.pat-date-tag { font-size: 8px; font-weight: 700; }
		.pat-date-tag--scheduled { fill: #2e7d52; }
		.pat-date-tag--actual { fill: #2c3e50; }
		.pat-date-label { font-size: 8px; font-weight: 600; }
		.pat-date-label--scheduled { fill: #2e7d52; }
		.pat-date-label--actual { fill: #2c3e50; }
		.pat-date-label-bg { fill: #fafbfc; stroke: #eef0f3; stroke-width: 0.5; }
		.pat-x-axis-day { fill: #5a6773; font-size: 10px; font-weight: 700; text-anchor: middle; }
		.pat-x-axis-title { fill: #8d99a6; font-size: 9px; font-weight: 600; text-anchor: middle; text-transform: uppercase; letter-spacing: 0.04em; }
		.pat-ongoing-tag { fill: #e67e22; font-size: 9px; font-weight: 700; }
		.pat-bar-overdue { fill: ${PAT_OVERDUE_COLOR}; cursor: pointer; }
		.pat-overdue-tag { fill: ${PAT_OVERDUE_COLOR}; font-size: 9px; font-weight: 700; dominant-baseline: middle; }
		.pat-overdue-tag-bg { fill: #fdecea; stroke: #f5b7b1; stroke-width: 0.8; }
		.pat-row-overdue { fill: ${PAT_OVERDUE_COLOR}; font-size: 8px; font-weight: 700; }
		.pat-empty { padding: 40px 20px; text-align: center; color: #8d99a6; font-size: 13px; line-height: 1.5; }
		.pat-table-heading { font-size: 13px; font-weight: 700; color: #1f272e; margin-top: 6px; }
		.pat-tooltip { position: absolute; display: none; min-width: 240px; max-width: 320px; padding: 12px 14px; background: #1f272e; color: #fff; border-radius: 8px; font-size: 11px; line-height: 1.5; box-shadow: 0 6px 20px rgba(0,0,0,0.18); pointer-events: none; z-index: 10; }
		.pat-tooltip-title { font-size: 13px; font-weight: 700; margin-bottom: 8px; }
		.pat-tooltip-row { display: flex; justify-content: space-between; gap: 12px; margin-top: 4px; }
		.pat-tooltip-row strong { font-weight: 700; }
		.pat-tooltip-divider { border-top: 1px solid rgba(255,255,255,0.15); margin: 8px 0 6px; }
		.pat-tooltip-section { font-size: 10px; color: #aeb6bf; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 6px; }
	`;

	$("<style>", { id: "pat-report-styles", text: css }).appendTo("head");
}

function pat_chart_rows(data) {
	return (data || [])
		.filter(
			(row) =>
				cint(row.has_scheduled_bar) ||
				cint(row.has_actual_bar) ||
				row.actual_start_date ||
				row.expected_start_date
		)
		.sort((a, b) => {
			const a_date = a.actual_chart_start_date || a.expected_chart_start_date || "";
			const b_date = b.actual_chart_start_date || b.expected_chart_start_date || "";
			return String(a_date).localeCompare(String(b_date));
		});
}

function pat_duration_days(start_value, end_value) {
	if (!start_value || !end_value) {
		return 0;
	}
	return frappe.datetime.get_day_diff(end_value, start_value) + 1;
}

function pat_format_date(value) {
	if (!value) {
		return "—";
	}
	return frappe.datetime.str_to_user(value);
}

function pat_status_color(status, fallback) {
	return PAT_STATUS_COLORS[status] || fallback || "#5dade2";
}

function pat_collect_summary(data) {
	const rows = data || [];
	const chart_rows = pat_chart_rows(rows);
	const ongoing = chart_rows.filter((row) => cint(row.is_ongoing)).length;
	const completed = chart_rows.filter((row) => row.status === "Completed").length;
	const late = chart_rows.filter((row) => row.schedule_status === "Late").length;
	const durations = chart_rows.map((row) => cint(row.duration_days)).filter((d) => d > 0);
	const avg_duration = durations.length
		? Math.round(durations.reduce((sum, d) => sum + d, 0) / durations.length)
		: 0;

	return {
		total: rows.length,
		chart_count: chart_rows.length,
		ongoing,
		completed,
		late,
		avg_duration,
		chart_rows,
	};
}

function pat_get_view_context(report) {
	const site_filter = report.get_filter_value("site_project");
	const from_date = report.get_filter_value("from_date");
	const to_date = report.get_filter_value("to_date");

	let view_label = __("All sites");
	let view_detail = __(
		"Each row is a site with dates rolled up from its kitchen units. Select Site Project to see unit timelines."
	);
	let row_label = __("Site");
	let table_heading = __("Detailed site list");

	if (site_filter) {
		view_label = __("Kitchen units for selected site");
		view_detail = __(
			"Each row is a kitchen unit under the selected site. Clear Site Project to return to all sites."
		);
		row_label = __("Project");
		table_heading = __("Detailed project list");
	}

	return {
		site_filter,
		view_label,
		view_detail,
		row_label,
		table_heading,
		range_label: `${pat_format_date(from_date)} — ${pat_format_date(to_date)}`,
	};
}

function pat_render_dashboard() {
	const report = frappe.query_report;
	const $form = report.page.main.find(".page-form");
	$(".pat-dashboard").remove();

	const data = report.data || [];
	const summary = pat_collect_summary(data);
	const context = pat_get_view_context(report);

	const $dash = $(`
		<div class="pat-dashboard">
			<div class="pat-header">
				<div class="pat-title">${__("Project timeline — scheduled vs actual")}</div>
				<div class="pat-context"></div>
			</div>
			<div class="pat-guide">
				<div class="pat-guide-card">
					<strong>${__("Top bar (light green dashed) = Scheduled")}</strong>
					${__("From Expected Start Date to Expected End Date — your original plan.")}
				</div>
				<div class="pat-guide-card">
					<strong>${__("Bottom bar (colour) = Actual")}</strong>
					${__("From Actual Start Date to Actual End Date. Open projects extend to today.")}
				</div>
				<div class="pat-guide-card">
					<strong>${__("X-axis = days")}</strong>
					${__("Every bar starts at Day 0. Length shows duration in days. Hover any bar for calendar dates.")}
				</div>
			</div>
			<div class="pat-kpi-grid"></div>
			<div class="pat-legend"></div>
			<div class="pat-chart-panel">
				<div class="pat-chart-head">
					<div class="pat-chart-row-label"></div>
					<div>${__("Timeline")}</div>
				</div>
				<div class="pat-chart-wrap">
					<div class="pat-chart-canvas"></div>
					<div class="pat-tooltip"></div>
				</div>
			</div>
			<div class="pat-table-heading"></div>
		</div>
	`);

	$form.after($dash);

	$dash.find(".pat-context").html(`
		<strong>${frappe.utils.escape_html(context.view_label)}</strong>
		· ${__("Period")}: ${frappe.utils.escape_html(context.range_label)}
		<br>${frappe.utils.escape_html(context.view_detail)}
	`);
	$dash.find(".pat-chart-row-label").text(context.row_label);
	$dash.find(".pat-table-heading").text(context.table_heading);

	pat_render_kpis($dash, summary, context);
	pat_render_legend($dash, summary.chart_rows);

	if (!summary.chart_rows.length) {
		$dash.find(".pat-chart-canvas").html(`
			<div class="pat-empty">
				<div style="font-weight:600;margin-bottom:6px">${__("No timeline bars to display")}</div>
				${__(
					"Sites or projects need Expected Start/End or Actual Start dates on kitchen units. Try widening the date range."
				)}
			</div>
		`);
		return;
	}

	pat_render_gantt($dash, summary.chart_rows);
}

function pat_render_kpis($dash, summary, context) {
	const cards = [
		{
			cls: "pat-kpi--blue",
			label: context.site_filter ? __("Projects shown") : __("Sites shown"),
			value: summary.chart_count,
			foot: context.site_filter ? __("kitchen units on chart") : __("sites on chart"),
		},
		{
			cls: "pat-kpi--orange",
			label: __("Still running"),
			value: summary.ongoing,
			foot: __("actual bar ends at today"),
		},
		{
			cls: "pat-kpi--green",
			label: __("Completed"),
			value: summary.completed,
			foot: __("with actual end date"),
		},
		{
			cls: "pat-kpi--red",
			label: __("Behind schedule"),
			value: summary.late,
			foot: summary.avg_duration
				? __("avg actual duration {0} days", [summary.avg_duration])
				: __("vs expected end"),
		},
	];

	$dash.find(".pat-kpi-grid").html(
		cards
			.map(
				(card) => `
			<div class="pat-kpi ${card.cls}">
				<div class="pat-kpi-label">${card.label}</div>
				<div class="pat-kpi-value">${card.value}</div>
				<div class="pat-kpi-foot">${card.foot}</div>
			</div>`
			)
			.join("")
	);
}

function pat_render_legend($dash, rows) {
	const statuses = [...new Set((rows || []).map((row) => row.status).filter(Boolean))];
	const status_items = statuses
		.map((status) => {
			const color = pat_status_color(status);
			return `<span class="pat-legend-item">
				<span class="pat-legend-swatch" style="background:${color}"></span>
				<span>${__("Actual")} · ${frappe.utils.escape_html(status)}</span>
			</span>`;
		})
		.join("");

	$dash.find(".pat-legend").html(`
		<span class="pat-legend-item">
			<span class="pat-legend-swatch pat-legend-swatch--scheduled"></span>
			<span>${__("Scheduled (expected start → end)")}</span>
		</span>
		${status_items}
		<span class="pat-legend-item">
			<span class="pat-legend-swatch" style="background:${PAT_OVERDUE_COLOR}"></span>
			<span>${__("Overdue days")}</span>
		</span>
	`);
}

function pat_axis_max_days(range_days) {
	return Math.max(
		PAT_AXIS_DAY_STEP,
		Math.ceil(range_days / PAT_AXIS_DAY_STEP) * PAT_AXIS_DAY_STEP
	);
}

function pat_build_scale(rows) {
	let max_days = 1;

	rows.forEach((row) => {
		if (cint(row.has_scheduled_bar)) {
			max_days = Math.max(
				max_days,
				pat_duration_days(row.expected_chart_start_date, row.expected_chart_end_date)
			);
		}
		if (cint(row.has_actual_bar) && row.actual_chart_start_date) {
			max_days = Math.max(
				max_days,
				cint(row.duration_days) ||
					pat_duration_days(row.actual_chart_start_date, row.actual_chart_end_date)
			);
		}
	});

	if (!max_days) {
		return null;
	}

	const range_days = max_days;
	const axis_max_days = pat_axis_max_days(range_days);
	const slot_min = Math.max(18, Math.min(64, 1100 / axis_max_days));
	const chart_w = Math.max(900, axis_max_days * slot_min);

	const day_scale = (days) => (days / axis_max_days) * chart_w;

	return { range_days, axis_max_days, chart_w, day_scale, max_days: range_days };
}

function pat_bar_center_y(row_y, bar_offset) {
	return row_y + bar_offset + PAT_ROW_LAYOUT.bar_h / 2;
}

function pat_draw_lane_label(svg, row_y, bar_offset, text, label_column_w) {
	const cy = pat_bar_center_y(row_y, bar_offset);
	svg += `<line class="pat-lane-guide" x1="68" y1="${cy}" x2="${label_column_w - 10}" y2="${cy}" />`;
	return `${svg}<text class="pat-row-lane" x="12" y="${cy}" dominant-baseline="middle">${frappe.utils.escape_html(
		text
	)}</text>`;
}

function pat_overdue_label(delay_days) {
	return __("{0}d overdue", [cint(delay_days)]);
}

function pat_draw_overdue_tag(svg, x, y, delay_days, options = {}) {
	const label = pat_overdue_label(delay_days);
	const safe = frappe.utils.escape_html(label);
	const pad_w = pat_estimate_label_width(label) + 10;
	const pad_h = 14;
	const pad_x = options.anchor === "end" ? x - pad_w : x;
	svg += `<rect class="pat-overdue-tag-bg" x="${pad_x}" y="${y - pad_h / 2}" width="${pad_w}" height="${pad_h}" rx="3" />`;
	return `${svg}<text class="pat-overdue-tag" x="${options.anchor === "end" ? x - 5 : x + 5}" y="${y}" text-anchor="${
		options.anchor === "end" ? "end" : "start"
	}" dominant-baseline="middle">${safe}</text>`;
}

function pat_draw_overdue_extension(svg, x, y, height, width, rowIdx) {
	if (!width || width <= 0) {
		return svg;
	}
	return `${svg}<rect class="pat-bar-overdue" data-row-idx="${rowIdx}" data-bar-type="actual"
		x="${x}" y="${y}" width="${width}" height="${height}" rx="4" ry="4" />`;
}

function pat_duration_bar_coords(day_scale, duration_days, min_width = 24) {
	if (!duration_days || duration_days <= 0) {
		return null;
	}

	const width = Math.max(day_scale(duration_days), min_width);
	return { x1: 0, width, duration_days };
}

function pat_estimate_label_width(text) {
	return String(text || "").length * 5.2 + 8;
}

function pat_draw_date_label(svg, x, y, text, kind, anchor = "middle") {
	if (!text || text === "—") {
		return svg;
	}
	const safe = frappe.utils.escape_html(text);
	const cls = kind === "scheduled" ? "pat-date-label--scheduled" : "pat-date-label--actual";
	const text_anchor =
		anchor === "start" ? "start" : anchor === "end" ? "end" : "middle";
	const pad_w = pat_estimate_label_width(text);
	const pad_x =
		anchor === "start" ? x - 2 : anchor === "end" ? x - pad_w + 2 : x - pad_w / 2;
	svg += `<rect class="pat-date-label-bg" x="${pad_x}" y="${y - 9}" width="${pad_w}" height="11" rx="2" />`;
	return `${svg}<text class="pat-date-label ${cls}" x="${x}" y="${y}" text-anchor="${text_anchor}">${safe}</text>`;
}

function pat_append_bar_date_labels(svg, x, bar_y, bar_h, width, startLabel, endLabel, kind, zone) {
	const label_y = zone === "above" ? bar_y - 5 : bar_y + bar_h + 13;
	const start = (startLabel || "").trim();
	const end = (endLabel || "").trim();
	if (!start && !end) {
		return svg;
	}

	const needs_combine =
		width < PAT_LABEL_MIN_GAP ||
		pat_estimate_label_width(start) + pat_estimate_label_width(end) + 12 > width;

	if (needs_combine) {
		const combined = start && end && start !== end ? `${start} → ${end}` : start || end;
		return pat_draw_date_label(svg, x + width / 2, label_y, combined, kind, "middle");
	}

	svg = pat_draw_date_label(svg, x + 2, label_y, start, kind, "start");
	return pat_draw_date_label(svg, x + width - 2, label_y, end, kind, "end");
}

function pat_draw_timeline_bar(svg, coords, y, height, options) {
	const {
		className,
		fill,
		stroke,
		rowIdx,
		barType,
		startLabel,
		endLabel,
		centerLabel,
		labelZone,
	} = options;

	const x = coords.x1;
	const w = coords.width;
	const radius = 4;

	svg += `<rect class="${className}" data-row-idx="${rowIdx}" data-bar-type="${barType}"
		x="${x}" y="${y}" width="${w}" height="${height}" rx="${radius}" ry="${radius}"
		fill="${fill}" ${stroke ? `stroke="${stroke}"` : ""} />`;

	svg = pat_append_bar_date_labels(
		svg,
		x,
		y,
		height,
		w,
		startLabel,
		endLabel,
		barType,
		labelZone
	);

	if (centerLabel && w >= 96) {
		svg += `<text fill="${barType === "scheduled" ? "#2e7d52" : "#fff"}" font-size="8" font-weight="700"
			text-anchor="middle" x="${x + w / 2}" y="${y + height / 2 + 3}" pointer-events="none">${frappe.utils.escape_html(
			centerLabel
		)}</text>`;
	}

	return svg;
}

function pat_render_gantt($dash, rows) {
	const label_w = 260;
	const pad = { top: 40, right: 48, bottom: 56, left: label_w };
	const { row_h, scheduled_bar_y, actual_bar_y, bar_h } = PAT_ROW_LAYOUT;
	const scale = pat_build_scale(rows);

	if (!scale) {
		$dash.find(".pat-chart-canvas").html(
			`<div class="pat-empty">${__("Unable to build timeline")}</div>`
		);
		return;
	}

	const { axis_max_days, chart_w, day_scale } = scale;
	const chart_h = pad.top + rows.length * row_h + pad.bottom;
	const width = chart_w + pad.left + pad.right;
	let svg = "";

	const axis_bottom = chart_h - pad.bottom;

	for (let day_num = 0; day_num <= axis_max_days; day_num += PAT_AXIS_DAY_STEP) {
		const x = pad.left + day_scale(day_num);
		svg += `<line class="pat-axis" x1="${x}" y1="${pad.top}" x2="${x}" y2="${axis_bottom}" />`;
		svg += `<text class="pat-x-axis-day" x="${x}" y="${axis_bottom + 16}" text-anchor="middle">${day_num}</text>`;
	}

	svg += `<text class="pat-x-axis-title" x="${pad.left + chart_w / 2}" y="${axis_bottom + 30}">${__(
		"Days"
	)}</text>`;

	svg += `<line class="pat-col-divider" x1="${pad.left}" y1="${pad.top - 10}" x2="${pad.left}" y2="${axis_bottom}" />`;

	rows.forEach((row, idx) => {
		const y = pad.top + idx * row_h;
		const row_bg = idx % 2 ? "pat-row-bg--alt" : "pat-row-bg";
		svg += `<rect class="${row_bg}" x="0" y="${y - 6}" width="${width}" height="${row_h}" />`;
		svg += `<line class="pat-row-divider" x1="0" y1="${y + row_h - 6}" x2="${width}" y2="${y + row_h - 6}" />`;

		const label = frappe.utils.escape_html(row.project_name || row.project);
		const delay_days = cint(row.delay_days);
		const is_late = row.schedule_status === "Late" && delay_days > 0;

		svg += `<text class="pat-row-label" x="12" y="${y + 14}">${label}</text>`;
		if (is_late) {
			svg += `<text class="pat-row-overdue" x="12" y="${y + 26}">${frappe.utils.escape_html(
				pat_overdue_label(delay_days)
			)}</text>`;
		}
		svg = pat_draw_lane_label(svg, y, scheduled_bar_y, __("Scheduled"), pad.left);
		svg = pat_draw_lane_label(svg, y, actual_bar_y, __("Actual"), pad.left);

		let sched = null;
		let sched_days = 0;
		if (cint(row.has_scheduled_bar)) {
			sched_days = pat_duration_days(
				row.expected_chart_start_date,
				row.expected_chart_end_date
			);
			sched = pat_duration_bar_coords(day_scale, sched_days, 28);
			if (sched) {
				svg = pat_draw_timeline_bar(
					svg,
					{ x1: pad.left + sched.x1, width: sched.width },
					y + scheduled_bar_y,
					bar_h,
					{
						className: "pat-bar-scheduled",
						fill: PAT_SCHEDULED_FILL,
						stroke: PAT_SCHEDULED_COLOR,
						rowIdx: idx,
						barType: "scheduled",
						labelZone: "above",
						startLabel: "0",
						endLabel: sched_days > 0 ? `${sched_days}d` : "",
						centerLabel: sched_days > 0 ? `${sched_days}d` : "",
					}
				);
			}
		}

		if (cint(row.has_actual_bar) && row.actual_chart_start_date) {
			const actual_days =
				cint(row.duration_days) ||
				pat_duration_days(row.actual_chart_start_date, row.actual_chart_end_date);
			const actual = pat_duration_bar_coords(day_scale, actual_days, 28);
			if (actual) {
				const color = row.status_color || pat_status_color(row.status);
				const is_ongoing = cint(row.is_ongoing);
				const actual_x = pad.left + actual.x1;
				const on_time_width =
					is_late && sched ? Math.min(sched.width, actual.width) : actual.width;
				const overdue_width =
					is_late && sched ? Math.max(actual.width - sched.width, 0) : 0;

				svg = pat_draw_timeline_bar(
					svg,
					{ x1: actual_x, width: on_time_width },
					y + actual_bar_y,
					bar_h,
					{
						className: "pat-bar-actual",
						fill: color,
						stroke: null,
						rowIdx: idx,
						barType: "actual",
						labelZone: "below",
						startLabel: "0",
						endLabel:
							is_late && overdue_width > 0
								? ""
								: is_ongoing
									? ""
									: actual_days > 0
										? `${actual_days}d`
										: "",
						centerLabel:
							is_late && overdue_width > 0
								? ""
								: actual_days > 0
									? `${actual_days}d`
									: "",
					}
				);

				if (overdue_width > 0) {
					svg = pat_draw_overdue_extension(
						svg,
						actual_x + on_time_width,
						y + actual_bar_y,
						bar_h,
						overdue_width,
						idx
					);
					const overdue_cy = pat_bar_center_y(y, actual_bar_y);
					const overdue_mid_x = actual_x + on_time_width + overdue_width / 2;
					if (overdue_width >= 36) {
						svg += `<text fill="#fff" font-size="8" font-weight="700" text-anchor="middle"
							x="${overdue_mid_x}" y="${overdue_cy + 3}" pointer-events="none">${frappe.utils.escape_html(
							pat_overdue_label(delay_days)
						)}</text>`;
					}
				}

				const tag_x = actual_x + actual.width + 8;
				const actual_cy = pat_bar_center_y(y, actual_bar_y);
				if (is_late) {
					svg = pat_draw_overdue_tag(svg, tag_x, actual_cy, delay_days);
				} else if (is_ongoing) {
					svg += `<text class="pat-ongoing-tag" x="${tag_x}" y="${actual_cy}" dominant-baseline="middle">${__(
						"ONGOING"
					)}</text>`;
				}
			}
		}
	});

	const html = `<svg class="pat-chart-svg" viewBox="0 0 ${width} ${chart_h}" width="${width}" height="${chart_h}" role="img" aria-label="${__(
		"Project timeline chart"
	)}">${svg}</svg>`;

	const $canvas = $dash.find(".pat-chart-canvas");
	const $tooltip = $dash.find(".pat-tooltip");
	$canvas.html(html);
	pat_bind_bar_tooltips($canvas, $tooltip, rows, $dash);
}

function pat_build_tooltip_html(row) {
	const title = frappe.utils.escape_html(row.project_name || row.project);
	const site = row.site_name ? frappe.utils.escape_html(row.site_name) : "";

	const unit_note =
		row.view_level === "site" && cint(row.unit_count) > 0
			? `<div style="color:#d1d8dd;margin-bottom:6px">${__(
					"Rolled up from {0} kitchen units",
					[cint(row.unit_count)]
			  )}</div>`
			: site
				? `<div style="color:#d1d8dd;margin-bottom:6px">${site}</div>`
				: "";

	return `
		<div class="pat-tooltip-title">${title}</div>
		${unit_note}
		<div class="pat-tooltip-section">${__("Scheduled")}</div>
		<div class="pat-tooltip-row"><span>${__("Start")}</span><strong>${pat_format_date(
			row.expected_start_date
		)}</strong></div>
		<div class="pat-tooltip-row"><span>${__("End")}</span><strong>${pat_format_date(
			row.expected_end_date
		)}</strong></div>
		<div class="pat-tooltip-divider"></div>
		<div class="pat-tooltip-section">${__("Actual")}</div>
		<div class="pat-tooltip-row"><span>${__("Start")}</span><strong>${pat_format_date(
			row.actual_start_date
		)}</strong></div>
		<div class="pat-tooltip-row"><span>${__("End")}</span><strong>${
			row.actual_end_date ? pat_format_date(row.actual_end_date) : __("Still running (today)")
		}</strong></div>
		<div class="pat-tooltip-row"><span>${__("Duration")}</span><strong>${
			row.duration_days ? __("{0} days", [row.duration_days]) : "—"
		}</strong></div>
		${
			row.schedule_status === "Late" && cint(row.delay_days) > 0
				? `<div class="pat-tooltip-divider"></div>
		<div class="pat-tooltip-row"><span>${__("Overdue")}</span><strong style="color:#ff6b6b">${__(
			"{0} days overdue",
			[cint(row.delay_days)]
		)}</strong></div>`
				: ""
		}
	`;
}

function pat_bind_bar_tooltips($canvas, $tooltip, rows, $dash) {
	$canvas.off("mousemove.pat mouseleave.pat click.pat");

	$canvas.on("mousemove.pat", ".pat-bar-scheduled, .pat-bar-actual, .pat-bar-overdue", function (e) {
		const idx = cint($(this).data("row-idx"));
		const row = rows[idx];
		if (!row) {
			return;
		}

		$tooltip.html(pat_build_tooltip_html(row)).show();

		const $wrap = $dash.find(".pat-chart-wrap");
		const wrap_rect = $wrap[0].getBoundingClientRect();
		let left = e.clientX - wrap_rect.left + 16;
		let top = e.clientY - wrap_rect.top + 12;
		const tip_w = 280;
		const tip_h = $tooltip.outerHeight() || 200;

		if (left + tip_w > $wrap.innerWidth() - 8) {
			left = e.clientX - wrap_rect.left - tip_w - 16;
		}
		if (top + tip_h > $wrap.innerHeight() - 8) {
			top = $wrap.innerHeight() - tip_h - 8;
		}

		$tooltip.css({ left, top });
		$(this).attr("opacity", "0.85");
	});

	$canvas.on("mouseleave.pat", ".pat-bar-scheduled, .pat-bar-actual, .pat-bar-overdue", function () {
		$tooltip.hide();
		$(this).attr("opacity", "1");
	});

	$canvas.on("mouseleave.pat", "svg", () => {
		$tooltip.hide();
		$canvas.find(".pat-bar-scheduled, .pat-bar-actual, .pat-bar-overdue").attr("opacity", "1");
	});

	$canvas.on("click.pat", ".pat-bar-scheduled, .pat-bar-actual, .pat-bar-overdue", function () {
		const idx = cint($(this).data("row-idx"));
		const row = rows[idx];
		if (row?.project) {
			frappe.set_route("Form", "Project", row.project);
		}
	});
}
