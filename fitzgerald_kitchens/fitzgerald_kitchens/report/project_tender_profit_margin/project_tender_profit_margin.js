// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const PTPM_REPORT_NAME = "Project Tender Profit Margin";

const PTPM_COST_SEGMENTS = [
	{ key: "manufacturing_actual_cost", label: __("Manufacturing Actual"), color: "#5dade2" },
	{ key: "task_actual_cost", label: __("Task Cost"), color: "#48c9b0" },
	{ key: "total_expense_claim", label: __("Expense Claims"), color: "#af7ac5" },
	{ key: "total_purchase_cost", label: __("Purchase Cost"), color: "#58d68d" },
	{ key: "total_consumed_material_cost", label: __("Material Cost"), color: "#f5b041" },
];

function ptpm_is_report(report) {
	if (report?.report_name) {
		return report.report_name === PTPM_REPORT_NAME;
	}
	const route = frappe.get_route();
	if (route[0] === "query-report") {
		return route[1] === PTPM_REPORT_NAME;
	}
	return frappe.query_report?.report_name === PTPM_REPORT_NAME;
}

function ptpm_teardown() {
	$(".ptpm-dashboard").remove();
}

function ptpm_register_route_teardown() {
	if (window._ptpm_route_teardown_registered) {
		return;
	}
	window._ptpm_route_teardown_registered = true;

	frappe.router.on("change", () => {
		const route = frappe.get_route();
		if (route[0] !== "query-report" || route[1] !== PTPM_REPORT_NAME) {
			ptpm_teardown();
		}
	});
}

ptpm_register_route_teardown();

frappe.query_reports[PTPM_REPORT_NAME] = {
	filters: [
		{
			label: __("Company"),
			fieldname: "company",
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
			on_change: function (query_report) {
				query_report.set_filter_value({
					site_project: "",
					kitchen_unit: "",
				});
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
			on_change: function (query_report) {
				const fiscal_year = query_report.get_values().fiscal_year;
				if (!fiscal_year) {
					return;
				}
				frappe.model.with_doc("Fiscal Year", fiscal_year, function () {
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
			reqd: 1,
		},
		{
			label: __("To Date"),
			fieldname: "to_date",
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[2],
			reqd: 1,
		},
		{
			label: __("Site Project"),
			fieldname: "site_project",
			fieldtype: "Link",
			options: "Project",
			reqd: 1,
			get_query: () => {
				const company = frappe.query_report?.get_filter_value("company");
				return {
					query:
						"fitzgerald_kitchens.fitzgerald_kitchens.report.project_tender_profit_margin.project_tender_profit_margin.site_project_query",
					filters: { company },
				};
			},
			on_change: function (query_report) {
				const site = query_report.get_filter_value("site_project");
				ptpm_apply_site_project_filter_label(site);

				const kitchen = query_report.get_filter_value("kitchen_unit");
				if (!site || !kitchen) {
					query_report.refresh();
					return;
				}
				frappe.db.get_value("Project", kitchen, "fk_parent_project").then((row) => {
					if (row?.fk_parent_project && row.fk_parent_project !== site) {
						query_report.set_filter_value("kitchen_unit", "");
					} else {
						query_report.refresh();
					}
				});
			},
		},
		{
			label: __("Kitchen Unit"),
			fieldname: "kitchen_unit",
			fieldtype: "Link",
			options: "Project",
			get_query: () => {
				const filters = { project_type: "Kitchen" };
				const site = ptpm_get_site_filter();
				if (site) {
					filters.fk_parent_project = site;
				}
				return { filters };
			},
		},
		{
			label: __("Work Order Status"),
			fieldname: "status",
			fieldtype: "Select",
			options: ["", "Not Started", "In Process", "Completed", "Stopped", "Closed"],
		},
	],

		onload() {
		ptpm_inject_styles();
		ptpm_hide_default_chrome();
		frappe.after_ajax(() => {
			ptpm_setup_site_project_filter();
			ptpm_hide_default_chrome();
		});
	},

	after_refresh() {
		if (!ptpm_is_report()) {
			return;
		}
		ptpm_hide_default_chrome();
		ptpm_setup_site_project_filter();
		ptpm_apply_site_project_filter_label();
		ptpm_render_dashboard().catch((error) => {
			console.error("[Project Tender Profit Margin]", error);
		});
	},

	get_chart_data() {
		return null;
	},

	after_datatable_render() {
		if (!ptpm_is_report()) {
			return;
		}
		ptpm_apply_site_project_filter_label();
		ptpm_render_dashboard().catch((error) => {
			console.error("[Project Tender Profit Margin]", error);
		});
	},

	formatter(value, row, column, data, default_formatter) {
		const margin_fields = ["profit_margin", "cost_variance", "margin_pct"];
		if (!margin_fields.includes(column.fieldname)) {
			return default_formatter(value, row, column, data);
		}

		const amount = flt(data?.[column.fieldname] ?? value);
		if (column.fieldname === "margin_pct") {
			if (!amount) {
				return default_formatter(value, row, column, data);
			}
			const color = amount >= 0 ? "green" : "red";
			return `<div style="color:${color}!important;font-weight:500;text-align:right;">${amount.toFixed(2)}%</div>`;
		}

		if (!amount) {
			return default_formatter(value, row, column, data);
		}

		const currency = column.options;
		let color = "var(--text-muted)";
		if (column.fieldname === "profit_margin") {
			color = amount >= 0 ? "green" : "red";
		} else if (column.fieldname === "cost_variance") {
			color = amount <= 0 ? "green" : "red";
		}

		return `<div style="color:${color}!important;font-weight:500;text-align:right;">${format_currency(
			Math.abs(amount),
			currency
		)}</div>`;
	},
};

function ptpm_build_chart_title(site_name) {
	const title = __("Kitchen Unit Cost vs Tender");
	const name = (site_name || "").trim();
	if (!name) {
		return title;
	}
	return `${title} (${frappe.utils.escape_html(name)})`;
}

function ptpm_resolve_chart_site_name(site_ctx, rows, site_filter) {
	if (site_ctx?.site_name) {
		return site_ctx.site_name;
	}
	const match = (rows || []).find((row) => row.site === site_filter);
	if (match?.site_name) {
		return match.site_name;
	}
	return site_filter || "";
}

function ptpm_format_site_project_label(name, project_name) {
	const code = (name || "").trim();
	const title = (project_name || "").trim();
	if (code && title) {
		return `${title} (${code})`;
	}
	return title || code;
}

function ptpm_parse_site_project_label(text) {
	const value = String(text || "").trim();
	if (!value) {
		return value;
	}

	const paren_match = value.match(/\(([^)]+)\)\s*$/);
	if (paren_match) {
		return paren_match[1].trim();
	}

	if (value.includes(" — ")) {
		return value.split(" — ", 1)[0].trim();
	}

	return value;
}

function ptpm_resolve_site_project_value(filter, raw_value) {
	let value = raw_value;
	if (value === undefined && filter) {
		if (filter.get_input_value) {
			value = filter.get_input_value();
		} else if (typeof filter.get_value === "function") {
			value = filter.get_value();
		}
	}

	if (!value) {
		return value;
	}

	const text = String(value).trim();
	const mapped = filter?.title_value_map?.[text];
	if (mapped) {
		return mapped;
	}

	return ptpm_parse_site_project_label(text);
}

function ptpm_get_site_project_filter() {
	return frappe.query_report?.get_filter?.("site_project");
}

function ptpm_get_site_filter() {
	const filter = ptpm_get_site_project_filter();
	if (!filter) {
		return frappe.query_report?.get_filter_value?.("site_project") || null;
	}
	const base_get_value = filter._ptpm_base_get_value || filter.get_value?.bind(filter);
	const raw = base_get_value ? base_get_value() : null;
	return ptpm_resolve_site_project_value(filter, raw) || null;
}

function ptpm_resolve_site_project_id(project_id, filter) {
	let resolved = (project_id || "").trim();
	if (!resolved && filter) {
		resolved = filter._ptpm_base_get_value?.() || filter.get_value?.() || "";
	}
	if (!resolved) {
		return "";
	}

	const mapped = filter?.title_value_map?.[resolved];
	if (mapped) {
		return mapped;
	}

	return ptpm_parse_site_project_label(resolved) || resolved;
}

function ptpm_set_site_project_filter_label(filter, name, project_name) {
	const label = ptpm_format_site_project_label(name, project_name);
	filter.title_value_map = filter.title_value_map || {};
	filter.title_value_map[label] = name;
	filter.set_input_value(label);
	frappe.utils.add_link_title("Project", name, label);
	return label;
}

function ptpm_apply_site_project_filter_label(project_id) {
	const filter = ptpm_get_site_project_filter();
	if (!filter) {
		return Promise.resolve();
	}

	const resolved = ptpm_resolve_site_project_id(project_id, filter);
	if (!resolved) {
		filter.set_input_value?.("");
		return Promise.resolve();
	}

	const cached = frappe.utils.get_link_title("Project", resolved);
	if (cached) {
		filter.title_value_map = filter.title_value_map || {};
		filter.title_value_map[cached] = resolved;
		filter.set_input_value(cached);
	}

	return frappe.db.get_value("Project", resolved, ["name", "project_name"]).then((row) => {
		if (row?.name) {
			ptpm_set_site_project_filter_label(filter, row.name, row.project_name);
		}
	});
}

function ptpm_setup_site_project_filter() {
	const filter = ptpm_get_site_project_filter();
	if (!filter || filter._ptpm_site_filter_patched) {
		return;
	}
	filter._ptpm_site_filter_patched = true;

	if (!filter._ptpm_base_get_value) {
		filter._ptpm_base_get_value = filter.get_value.bind(filter);
		filter.get_value = function () {
			return ptpm_resolve_site_project_value(this, filter._ptpm_base_get_value());
		};
	}

	if (filter.set_input && !filter._ptpm_base_set_input) {
		filter._ptpm_base_set_input = filter.set_input.bind(filter);
		filter.set_input = function (value) {
			filter._ptpm_base_set_input(value);
			if (value) {
				ptpm_apply_site_project_filter_label(value);
			}
		};
	}

	filter.set_link_title = async function (value) {
		await ptpm_apply_site_project_filter_label(
			ptpm_resolve_site_project_value(this, value)
		);
	};

	if (filter.$input && !filter._ptpm_awesomplete_hooked) {
		filter._ptpm_awesomplete_hooked = true;
		filter.$input.on("awesomplete-selectcomplete.ptpm", () => {
			ptpm_apply_site_project_filter_label(filter._ptpm_base_get_value?.());
		});
	}

	ptpm_apply_site_project_filter_label();
}

function ptpm_inject_styles() {
	if (document.getElementById("ptpm-report-styles-v7")) {
		return;
	}
	frappe.dom.set_style(`
		.ptpm-dashboard { margin-bottom: 16px; }
		.ptpm-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; padding: 16px 0; }
		@media (max-width: 1100px) { .ptpm-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
		@media (max-width: 640px) { .ptpm-kpi-grid { grid-template-columns: 1fr; } }
		.ptpm-kpi-card { border-radius: 10px; padding: 14px 16px; min-height: 96px; display: flex; flex-direction: column; justify-content: space-between; border: 1px solid rgba(0,0,0,0.04); }
		.ptpm-kpi-card--grey { background: #f4f6f8; }
		.ptpm-kpi-card--green { background: #eafaf1; }
		.ptpm-kpi-card--red { background: #fdecea; }
		.ptpm-kpi-card--orange { background: #fef5e7; }
		.ptpm-kpi-label { font-size: 11px; font-weight: 600; color: #6c7a89; line-height: 1.3; }
		.ptpm-kpi-value { font-size: 28px; font-weight: 800; line-height: 1.1; margin: 6px 0; color: #1f272e; }
		.ptpm-kpi-value--green { color: #1e8449; }
		.ptpm-kpi-value--red { color: #c0392b; }
		.ptpm-kpi-value--orange { color: #d68910; }
		.ptpm-kpi-foot { font-size: 11px; color: #8d99a6; line-height: 1.35; }
		.ptpm-legend {
			display: flex;
			flex-wrap: wrap;
			align-items: center;
			gap: 14px;
			padding: 10px 0 14px;
			border-bottom: 1px solid #eef0f3;
			font-size: 11px;
			color: #5a6773;
		}
		.ptpm-legend-item { display: inline-flex; align-items: center; gap: 6px; }
		.ptpm-legend-swatch { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
		.ptpm-legend-cutoff { margin-left: auto; color: #c0392b; font-weight: 600; white-space: nowrap; }
		.ptpm-chart-panel { border: 1px solid #e8eaed; border-radius: 10px; padding: 16px 16px 8px; margin-top: 4px; background: #fff; }
		.ptpm-chart-title { font-size: 14px; font-weight: 700; color: #1f272e; margin: 0; }
		.ptpm-chart-sub { font-size: 11px; color: #8d99a6; margin-top: 4px; margin-bottom: 12px; }
		.ptpm-site-banner {
			display: flex;
			flex-wrap: wrap;
			align-items: flex-start;
			gap: 8px 20px;
			padding: 12px 14px;
			margin-bottom: 12px;
			background: #f4f8fb;
			border-radius: 8px;
			border-left: 4px solid #5dade2;
		}
		.ptpm-site-banner--delayed { background: #fdf6f5; border-left-color: #e74c3c; }
		.ptpm-site-banner-main { flex: 1 1 220px; min-width: 0; }
		.ptpm-site-banner-name { font-size: 15px; font-weight: 800; color: #1f272e; line-height: 1.25; }
		.ptpm-site-banner-code { font-size: 11px; color: #8d99a6; margin-top: 2px; }
		.ptpm-site-banner-meta {
			display: flex;
			flex-wrap: wrap;
			gap: 10px 18px;
			flex: 2 1 320px;
		}
		.ptpm-site-banner-item { min-width: 120px; }
		.ptpm-site-banner-label { font-size: 10px; font-weight: 600; color: #8d99a6; text-transform: uppercase; letter-spacing: 0.02em; }
		.ptpm-site-banner-value { font-size: 12px; font-weight: 700; color: #1f272e; margin-top: 2px; }
		.ptpm-site-banner-value--tender { color: #c0392b; }
		.ptpm-site-banner-badge {
			display: inline-block;
			margin-top: 6px;
			padding: 2px 8px;
			border-radius: 999px;
			font-size: 10px;
			font-weight: 700;
			background: #fdecea;
			color: #c0392b;
		}
		.ptpm-chart-wrap { width: 100%; overflow-x: auto; position: relative; }
		.ptpm-chart-canvas svg { cursor: crosshair; }
		.ptpm-chart-tooltip {
			position: fixed;
			display: none;
			min-width: 200px;
			max-width: 300px;
			padding: 10px 12px;
			background: #1f272e;
			color: #fff;
			border-radius: 8px;
			font-size: 11px;
			line-height: 1.45;
			box-shadow: 0 4px 16px rgba(0,0,0,0.18);
			pointer-events: none;
			z-index: 9999;
		}
		.ptpm-chart-tooltip-title { font-size: 12px; font-weight: 700; margin-bottom: 6px; color: #fff; }
		.ptpm-chart-tooltip-row { display: flex; justify-content: space-between; gap: 12px; margin-top: 3px; }
		.ptpm-chart-tooltip-row strong { font-weight: 700; color: #fff; }
		.ptpm-chart-tooltip-row--tender strong { color: #f1948a; }
		.ptpm-chart-tooltip-row--ok strong { color: #58d68d; }
		.ptpm-chart-tooltip-row--over strong { color: #f1948a; }
		.ptpm-chart-tooltip-row--profit strong { color: #58d68d; }
		.ptpm-chart-tooltip-row--loss strong { color: #f1948a; }
		.ptpm-chart-tooltip-divider { border-top: 1px solid rgba(255,255,255,0.15); margin: 8px 0 6px; }
		.ptpm-chart-tooltip-meta { color: #d1d8dd; margin-top: 2px; }
		.ptpm-chart-hover-line { stroke: #aeb6bf; stroke-width: 1; stroke-dasharray: 3 3; pointer-events: none; }
		.ptpm-chart-hover-cutoff { fill: #e74c3c; stroke: #fff; stroke-width: 1.5; pointer-events: none; }
		.ptpm-chart-svg { display: block; min-width: 640px; }
		.ptpm-chart-axis { stroke: #e8eaed; stroke-width: 1; }
		.ptpm-chart-cutoff-line { stroke: #e74c3c; stroke-width: 2; stroke-dasharray: 6 4; fill: none; pointer-events: none; }
		.ptpm-chart-cutoff-label { fill: #e74c3c; font-size: 10px; font-weight: 600; pointer-events: none; }
		.ptpm-chart-seg-label { fill: #fff; font-size: 10px; font-weight: 700; text-anchor: middle; pointer-events: none; }
		.ptpm-chart-margin-label { font-size: 11px; font-weight: 700; text-anchor: middle; pointer-events: none; }
		.ptpm-chart-margin-label--profit { fill: #27ae60; }
		.ptpm-chart-margin-label--loss { fill: #c0392b; }
		.ptpm-chart-x-label { fill: #8d99a6; font-size: 10px; font-weight: 600; text-anchor: middle; }
		.ptpm-chart-x-label--sub { fill: #aeb6bf; font-size: 9px; font-weight: 600; text-anchor: middle; }
		.ptpm-chart-x-label--rotated { text-anchor: end; }
		.ptpm-chart-y-label { fill: #aeb6bf; font-size: 10px; text-anchor: end; }
		.ptpm-table-heading { font-size: 13px; font-weight: 700; color: #1f272e; padding: 18px 0 8px; border-top: 1px solid #eef0f3; margin-top: 8px; }
	`, "ptpm-report-styles-v7");
}

function ptpm_get_report_rows() {
	const result =
		frappe.query_report?.raw_data?.result || frappe.query_report?.data || [];
	return (result || []).filter(
		(row) =>
			row &&
			!row.is_total_row &&
			row.kitchen_unit &&
			String(row.kitchen_unit).trim() &&
			row.kitchen_unit !== __("Total")
	);
}

function ptpm_compute_unit_total_cost(row) {
	return PTPM_COST_SEGMENTS.reduce((sum, seg) => sum + flt(row?.[seg.key]), 0);
}

function ptpm_unit_total_cost(unit) {
	const segment_total = unit.segments.reduce((sum, seg) => sum + flt(seg.value), 0);
	const row_total = flt(unit.row?.total_cost);
	if (row_total > 0 && Math.abs(row_total - flt(unit.row?.profit_margin)) > 0.001) {
		return row_total;
	}
	return segment_total || row_total;
}

function ptpm_profit_margin_tooltip_class(margin) {
	return flt(margin) >= 0 ? "ptpm-chart-tooltip-row--profit" : "ptpm-chart-tooltip-row--loss";
}

function ptpm_profit_margin_bar_class(margin_pct) {
	return flt(margin_pct) >= 0 ? "ptpm-chart-margin-label--profit" : "ptpm-chart-margin-label--loss";
}

function ptpm_unit_profit_margin(unit) {
	return flt(unit.profit_margin ?? unit.row?.profit_margin);
}

function ptpm_unit_margin_pct(unit) {
	return flt(unit.margin_pct ?? unit.row?.margin_pct);
}

function ptpm_is_kitchen_completed(unit) {
	return cint(unit.is_kitchen_completed ?? unit.row?.is_kitchen_completed) === 1;
}

function ptpm_format_chart_bar_margin_pct(value) {
	return `${Math.round(flt(value))}%`;
}

function ptpm_format_currency(value) {
	const currency =
		frappe.query_report?.columns?.find((col) => col.fieldtype === "Currency")?.options ||
		frappe.defaults.get_default("currency");
	return format_currency(flt(value), currency);
}

function ptpm_chart_axis_label(row) {
	const code = (row.kitchen_unit || "").trim();
	const name = (row.kitchen_name || "").trim();
	if (code) {
		if (code.length <= 14) {
			return code;
		}
		const parts = code.split("-");
		if (parts.length >= 2) {
			return parts.slice(-2).join("-");
		}
		return code;
	}
	return name || code;
}

function ptpm_estimate_label_width(text, font_size = 10) {
	return Math.max(28, (text || "").length * (font_size * 0.62));
}

function ptpm_chart_layout(units) {
	const axis_labels = units.map((unit) => ptpm_chart_axis_label(unit.row));
	const max_label_width = Math.max(...axis_labels.map((label) => ptpm_estimate_label_width(label)), 48);
	const period_count = units.length;
	const slot_min = Math.max(period_count > 12 ? 64 : 80, Math.ceil(max_label_width + 16));
	const width = Math.max(640, period_count * slot_min + 80);
	const pad = { top: 28, right: 72, left: 36 };
	const chart_w = width - pad.left - pad.right;
	const slot_w = Math.max(chart_w / period_count, 1);
	const rotate_labels = slot_w < max_label_width + 8;
	pad.bottom = rotate_labels ? 78 : 52;
	const height = rotate_labels ? 334 : 310;
	const chart_h = height - pad.top - pad.bottom;

	return {
		axis_labels,
		width,
		height,
		pad,
		chart_w,
		chart_h,
		slot_w,
		slot_min,
		rotate_labels,
	};
}

function ptpm_split_kitchen_label(label, max_width = 72) {
	const text = (label || "").trim();
	if (!text) {
		return { line1: "", line2: "", mode: "single" };
	}

	const max_chars = Math.max(8, Math.floor(max_width / 6.2));
	if (text.length <= max_chars) {
		return { line1: text, line2: "", mode: "single" };
	}

	if (text.includes("|")) {
		const parts = text.split("|").map((p) => p.trim()).filter(Boolean);
		if (parts.length >= 2) {
			return { line1: parts[0], line2: parts.slice(1).join(" · "), mode: "double" };
		}
	}

	const space = text.lastIndexOf(" ", max_chars);
	if (space > 4) {
		return {
			line1: text.slice(0, space),
			line2: text.slice(space + 1),
			mode: "double",
		};
	}

	return { line1: `${text.slice(0, max_chars - 1)}…`, line2: "", mode: "single" };
}

function ptpm_render_x_axis_label(cx, base_y, label, layout) {
	const { slot_w, rotate_labels } = layout;
	const safe = frappe.utils.escape_html(label);

	if (rotate_labels) {
		return `
			<text class="ptpm-chart-x-label ptpm-chart-x-label--rotated"
				x="${cx}" y="${base_y}"
				transform="rotate(-42, ${cx}, ${base_y})"
				text-anchor="end">${safe}</text>`;
	}

	const { line1, line2, mode } = ptpm_split_kitchen_label(label, slot_w - 8);
	const safe1 = frappe.utils.escape_html(line1);
	const safe2 = frappe.utils.escape_html(line2);

	if (mode === "double" && line2) {
		return `
			<text class="ptpm-chart-x-label" x="${cx}" y="${base_y - 12}" text-anchor="middle">${safe1}</text>
			<text class="ptpm-chart-x-label ptpm-chart-x-label--sub" x="${cx}" y="${base_y + 1}" text-anchor="middle">${safe2}</text>`;
	}

	return `<text class="ptpm-chart-x-label" x="${cx}" y="${base_y - 4}" text-anchor="middle">${safe1}</text>`;
}

function ptpm_collect_chart_data(rows) {
	return (rows || []).map((row) => {
		const segments = PTPM_COST_SEGMENTS.map((seg) => ({
			...seg,
			value: flt(row[seg.key]),
		}));
		const total_cost = ptpm_compute_unit_total_cost(row);

		return {
			label: row.kitchen_name || row.kitchen_unit,
			axis_label: ptpm_chart_axis_label(row),
			kitchen_unit: row.kitchen_unit,
			site_name: row.site_name || row.site,
			tender_name: row.tender_name || row.tender_configuration,
			total_cost,
			tender: flt(row.tender_price_per_kitchen),
			profit_margin: flt(row.profit_margin),
			margin_pct: flt(row.margin_pct),
			over_tender: total_cost > flt(row.tender_price_per_kitchen),
			segments,
			row,
		};
	});
}

function ptpm_collect_kpi_data(units) {
	const site_names = [...new Set(units.map((u) => u.row.site).filter(Boolean))];
	const delayed_sites = [];
	const seen_delayed = new Set();
	units.forEach((unit) => {
		if (!cint(unit.row.is_site_delayed) || seen_delayed.has(unit.row.site)) {
			return;
		}
		seen_delayed.add(unit.row.site);
		delayed_sites.push({
			site: unit.row.site,
			site_name: unit.row.site_name || unit.row.site,
		});
	});
	const over_units = units.filter((u) => u.over_tender);
	const margin_pcts = units.map((u) => u.margin_pct);
	const margins = units.map((u) => u.profit_margin);
	const avg_margin_pct = margin_pcts.length
		? margin_pcts.reduce((sum, pct) => sum + pct, 0) / margin_pcts.length
		: 0;
	const avg_profit_margin = margins.length
		? margins.reduce((sum, margin) => sum + margin, 0) / margins.length
		: 0;

	return {
		unit_count: units.length,
		site_count: site_names.length,
		delayed_sites,
		delayed_count: delayed_sites.length,
		avg_margin_pct,
		avg_profit_margin,
		over_units,
		over_count: over_units.length,
	};
}

function ptpm_margin_status(avg_margin_pct) {
	if (avg_margin_pct < 0) {
		return __("below tender on average");
	}
	if (avg_margin_pct >= 15) {
		return __("healthy margin across units");
	}
	return __("margin headroom available");
}

function ptpm_margin_value_class(avg_margin_pct) {
	if (avg_margin_pct < 0) {
		return "ptpm-kpi-value--red";
	}
	if (avg_margin_pct >= 15) {
		return "ptpm-kpi-value--green";
	}
	return "ptpm-kpi-value--orange";
}

function ptpm_over_tender_foot(over_units) {
	if (!over_units.length) {
		return __("all kitchen units within tender");
	}

	const labels = over_units
		.slice(0, 2)
		.map((u) => ptpm_split_kitchen_label(u.label).line1 || u.label);
	let foot = labels.join(", ");
	if (over_units.length > 2) {
		foot += ` +${over_units.length - 2}`;
	}
	return `${foot} · ${__("review cost overrun")}`;
}

function ptpm_delayed_projects_foot(delayed_sites) {
	if (!delayed_sites.length) {
		return __("all site projects on schedule");
	}

	const labels = delayed_sites.slice(0, 2).map((site) => site.site_name);
	let foot = labels.join(", ");
	if (delayed_sites.length > 2) {
		foot += ` +${delayed_sites.length - 2}`;
	}
	return `${foot} · ${__("past expected end date")}`;
}

function ptpm_filter_rows_for_site(rows) {
	const site_filter = ptpm_get_site_filter();
	if (!site_filter) {
		return [];
	}
	return (rows || []).filter((row) => row.site === site_filter);
}

async function ptpm_get_site_context(rows) {
	const site_filter = ptpm_get_site_filter();
	if (!site_filter) {
		return null;
	}

	const site_rows = (rows || []).filter((row) => row.site === site_filter);
	const sample = site_rows[0];

	const site = await frappe.db.get_value("Project", site_filter, [
		"name",
		"project_name",
		"fk_tender_configuration",
		"fk_tender_price_per_kitchen",
		"expected_end_date",
		"status",
	]);
	if (!site?.name) {
		return null;
	}

	let tender = {};
	if (site.fk_tender_configuration) {
		tender =
			(await frappe.db.get_value("Tender Configuration", site.fk_tender_configuration, [
				"name",
				"tender_name",
				"tender_price_per_kitchen",
			])) || {};
	}

	const tender_price =
		ptpm_resolve_tender_price_per_kitchen(site, tender) ||
		flt(sample?.tender_price_per_kitchen);

	const today = frappe.datetime.get_today();
	const is_delayed =
		site.expected_end_date &&
		site.expected_end_date < today &&
		!["Completed", "Cancelled"].includes(site.status);

	return {
		site: site.name,
		site_name: site.project_name || site.name,
		tender_configuration: tender.name || site.fk_tender_configuration,
		tender_name: tender.tender_name || tender.name || site.fk_tender_configuration,
		tender_price,
		is_delayed: sample ? site_rows.some((row) => cint(row.is_site_delayed)) : is_delayed,
		kitchen_count: site_rows.length,
	};
}

function ptpm_resolve_tender_price_per_kitchen(site, tender) {
	const from_tender = flt(tender?.tender_price_per_kitchen);
	if (from_tender) {
		return from_tender;
	}
	const from_project = flt(site?.fk_tender_price_per_kitchen);
	if (from_project) {
		return from_project;
	}
	return 0;
}

function ptpm_get_chart_tender_price(site_ctx, units) {
	const from_ctx = flt(site_ctx?.tender_price);
	if (from_ctx) {
		return from_ctx;
	}
	for (const unit of units || []) {
		const from_row = flt(unit.tender) || flt(unit.row?.tender_price_per_kitchen);
		if (from_row) {
			return from_row;
		}
	}
	return 0;
}

function ptpm_site_banner_html(site_ctx) {
	const delayed_badge = site_ctx.is_delayed
		? `<span class="ptpm-site-banner-badge">${__("Delayed")}</span>`
		: "";
	const tender_price = site_ctx.tender_price
		? ptpm_format_currency(site_ctx.tender_price)
		: __("Not set");

	return `
		<div class="ptpm-site-banner ${site_ctx.is_delayed ? "ptpm-site-banner--delayed" : ""}">
			<div class="ptpm-site-banner-main">
				<div class="ptpm-site-banner-name">${frappe.utils.escape_html(site_ctx.site_name)}</div>
				<div class="ptpm-site-banner-code">${frappe.utils.escape_html(site_ctx.site)}</div>
				${delayed_badge}
			</div>
			<div class="ptpm-site-banner-meta">
				<div class="ptpm-site-banner-item">
					<div class="ptpm-site-banner-label">${__("Tender")}</div>
					<div class="ptpm-site-banner-value">${frappe.utils.escape_html(site_ctx.tender_name || "—")}</div>
				</div>
				<div class="ptpm-site-banner-item">
					<div class="ptpm-site-banner-label">${__("Tender Price Per Kitchen")}</div>
					<div class="ptpm-site-banner-value ptpm-site-banner-value--tender">${tender_price}</div>
				</div>
				<div class="ptpm-site-banner-item">
					<div class="ptpm-site-banner-label">${__("Kitchen Units")}</div>
					<div class="ptpm-site-banner-value">${site_ctx.kitchen_count}</div>
				</div>
			</div>
		</div>`;
}

function ptpm_render_kpi_cards($dash, kpi) {
	const cards = [
		{
			cls: "ptpm-kpi-card--grey",
			label: __("Delayed projects"),
			value: kpi.delayed_count,
			value_cls: kpi.delayed_count > 0 ? "ptpm-kpi-value--red" : "",
			foot: ptpm_delayed_projects_foot(kpi.delayed_sites),
		},
		{
			cls: "ptpm-kpi-card--green",
			label: __("Avg margin %"),
			value: `${Math.round(kpi.avg_margin_pct)}%`,
			value_cls: ptpm_margin_value_class(kpi.avg_margin_pct),
			foot: ptpm_margin_status(kpi.avg_margin_pct),
		},
		{
			cls: "ptpm-kpi-card--red",
			label: __("Units over tender"),
			value: kpi.over_count,
			value_cls: kpi.over_count > 0 ? "ptpm-kpi-value--red" : "",
			foot: ptpm_over_tender_foot(kpi.over_units),
		},
		{
			cls: "ptpm-kpi-card--orange",
			label: __("Avg profit margin"),
			value: ptpm_format_currency(kpi.avg_profit_margin),
			value_cls: kpi.avg_profit_margin >= 0 ? "ptpm-kpi-value--orange" : "ptpm-kpi-value--red",
			foot: __("average per kitchen unit"),
		},
	];

	const html = cards
		.map(
			(card) => `
		<div class="ptpm-kpi-card ${card.cls}">
			<div class="ptpm-kpi-label">${card.label}</div>
			<div class="ptpm-kpi-value ${card.value_cls}">${card.value}</div>
			<div class="ptpm-kpi-foot">${card.foot}</div>
		</div>`
		)
		.join("");

	$dash.find(".ptpm-kpi-grid").html(html);
}

function ptpm_teardown() {
	$(".ptpm-dashboard").remove();
}

function ptpm_hide_default_chrome() {
	$(".chart-wrapper").hide().empty();
	$(".report-summary").hide().empty();

	const report = frappe.query_report;
	if (report?.$chart) {
		report.$chart.hide().empty();
		if (report.chart) {
			report.chart = null;
		}
	}
	if (report?.$summary) {
		report.$summary.hide().empty();
	}
}

let ptpm_render_token = 0;

async function ptpm_render_dashboard() {
	const render_token = ++ptpm_render_token;
	ptpm_teardown();
	ptpm_hide_default_chrome();

	const site_filter = ptpm_get_site_filter();
	let rows = ptpm_get_report_rows();
	rows = ptpm_filter_rows_for_site(rows);

	const $target = $(".report-wrapper").first();
	if (!$target.length) {
		return;
	}

	const site_ctx = site_filter ? await ptpm_get_site_context(rows) : null;
	if (render_token !== ptpm_render_token) {
		return;
	}

	const from_date = frappe.query_report.get_filter_value("from_date");
	const to_date = frappe.query_report.get_filter_value("to_date");
	const from_label = from_date ? frappe.datetime.str_to_user(from_date) : "";
	const to_label = to_date ? frappe.datetime.str_to_user(to_date) : "";

	const chart_site_name = ptpm_resolve_chart_site_name(site_ctx, rows, site_filter);
	const chart_title = ptpm_build_chart_title(chart_site_name);
	const chart_sub = site_ctx
		? `${__("Kitchen units under selected site only")} · ${__(
				"Tender Price Per Kitchen"
		  )} ${ptpm_format_currency(site_ctx.tender_price)} ${__(
				"from linked tender"
		  )} · ${from_label} — ${to_label}`
		: __("Select a Site Project to view kitchen unit costs against the site tender");

	const dashboard = $(`
		<div class="ptpm-dashboard">
			<div class="ptpm-kpi-grid"></div>
			<div class="ptpm-legend"></div>
			<div class="ptpm-chart-panel">
				${site_ctx ? ptpm_site_banner_html(site_ctx) : ""}
				<div class="ptpm-chart-title">${chart_title}</div>
				<div class="ptpm-chart-sub">${chart_sub}</div>
				<div class="ptpm-chart-wrap">
					<div class="ptpm-chart-canvas"></div>
					<div class="ptpm-chart-tooltip"></div>
				</div>
			</div>
			${site_filter ? `<div class="ptpm-table-heading">${__("Detailed cost breakdown")}</div>` : ""}
		</div>
	`);

	$target.before(dashboard);
	if (render_token !== ptpm_render_token) {
		dashboard.remove();
		return;
	}

	const $dash = dashboard;

	if (!site_filter) {
		ptpm_render_empty_chart($dash, __("Select a Site Project to view the chart"));
		ptpm_render_kpi_cards($dash, ptpm_empty_kpi_data());
		ptpm_render_legend($dash, [], null);
		return;
	}

	const units = ptpm_collect_chart_data(rows);
	const kpi = ptpm_collect_kpi_data(units);
	ptpm_render_kpi_cards($dash, kpi);
	ptpm_render_legend($dash, units, site_ctx);
	ptpm_render_chart($dash, units, site_ctx);
}

function ptpm_empty_kpi_data() {
	return {
		unit_count: 0,
		site_count: 0,
		delayed_sites: [],
		delayed_count: 0,
		avg_margin_pct: 0,
		avg_profit_margin: 0,
		over_units: [],
		over_count: 0,
	};
}

function ptpm_render_empty_chart($dash, message) {
	$dash.find(".ptpm-chart-canvas").html(
		`<div style="padding:40px;text-align:center;color:#8d99a6">${message}</div>`
	);
}

function ptpm_render_legend($dash, units, site_ctx) {
	const segment_legend = PTPM_COST_SEGMENTS.map(
		(seg) => `
		<span class="ptpm-legend-item">
			<span class="ptpm-legend-swatch" style="background:${seg.color}"></span>
			<span>${seg.label}</span>
		</span>`
	).join("");

	let tender_label = __("Not set");
	if (site_ctx?.tender_price) {
		tender_label = ptpm_format_currency(site_ctx.tender_price);
	}

	$dash.find(".ptpm-legend").html(`
		${segment_legend}
		<span class="ptpm-legend-cutoff">— — — ${__("Tender Price Per Kitchen")} (${tender_label})</span>
	`);
}

function ptpm_render_chart($dash, units, site_ctx) {
	if (!units.length) {
		ptpm_render_empty_chart(
			$dash,
			site_ctx?.tender_price
				? __("No kitchen units found for this site")
				: __("This site has no linked Tender Configuration")
		);
		return;
	}

	const layout = ptpm_chart_layout(units);
	let { width, height, pad, chart_w, chart_h, slot_w } = layout;

	const tender_price = ptpm_get_chart_tender_price(site_ctx, units);
	const tender_label_text =
		tender_price > 0 ? `${__("Tender Price Per Kitchen")}: ${Math.round(tender_price)}` : "";
	if (tender_label_text) {
		const tender_label_w = ptpm_estimate_label_width(tender_label_text, 10);
		const needed_right = tender_label_w + 14;
		if (needed_right > pad.right) {
			width += needed_right - pad.right;
			pad.right = needed_right;
			chart_w = width - pad.left - pad.right;
			slot_w = Math.max(chart_w / units.length, 1);
		}
	}

	let bar_w = Math.max(8, Math.min(42, slot_w - 12));

	const max_total = Math.max(...units.map((u) => ptpm_unit_total_cost(u)), 0);
	const y_max = Math.max(max_total, tender_price, 1);
	const y_scale = (val) => pad.top + chart_h - (val / y_max) * chart_h;

	let bars_svg = "";

	units.forEach((unit, idx) => {
		const cx = pad.left + slot_w * idx + slot_w / 2;
		let y_cursor = pad.top + chart_h;
		const total_cost = ptpm_unit_total_cost(unit);
		const stack_total = unit.segments.reduce((sum, seg) => sum + seg.value, 0);
		const bar_total = total_cost > 0 ? total_cost : stack_total;

		unit.segments.forEach((seg) => {
			if (!seg.value) {
				return;
			}
			const share = stack_total > 0 ? seg.value / stack_total : 0;
			const seg_val = bar_total * share;
			const seg_h = (seg_val / y_max) * chart_h;
			if (seg_h <= 0) {
				return;
			}
			const y = y_cursor - seg_h;
			bars_svg += `
				<rect x="${cx - bar_w / 2}" y="${y}" width="${bar_w}" height="${seg_h}" fill="${seg.color}" rx="2"></rect>`;
			if (seg_h >= 12 && seg.value > 0) {
				bars_svg += `<text class="ptpm-chart-seg-label" x="${cx}" y="${y + seg_h / 2 + 4}">${Math.round(
					seg.value
				)}</text>`;
			}
			y_cursor = y;
		});

		const margin_pct = ptpm_unit_margin_pct(unit);
		const margin_cls = ptpm_profit_margin_bar_class(margin_pct);
		const has_bar = total_cost > 0 || stack_total > 0;
		if (ptpm_is_kitchen_completed(unit)) {
			const label_y = (has_bar ? y_cursor : y_scale(0)) - 3;
			bars_svg += `<text class="ptpm-chart-margin-label ${margin_cls}" x="${cx}" y="${label_y}">${ptpm_format_chart_bar_margin_pct(
				margin_pct
			)}</text>`;
		}

		bars_svg += ptpm_render_x_axis_label(cx, height - 10, unit.axis_label || unit.label, layout);
	});

	let grid_svg = "";
	const y_ticks = 5;
	for (let i = 0; i <= y_ticks; i += 1) {
		const val = Math.round((y_max / y_ticks) * i);
		const y = y_scale(val);
		grid_svg += `<line class="ptpm-chart-axis" x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" />`;
		grid_svg += `<text class="ptpm-chart-y-label" x="${pad.left - 6}" y="${y + 4}">${val}</text>`;
	}

	const cutoff_y = y_scale(tender_price);
	const tender_line_svg =
		tender_price > 0
			? `<line class="ptpm-chart-cutoff-line" x1="${pad.left}" y1="${cutoff_y}" x2="${width - pad.right}" y2="${cutoff_y}" />`
			: "";
	const tender_label_svg =
		tender_price > 0
			? `<text class="ptpm-chart-cutoff-label" x="${width - 8}" y="${cutoff_y}" text-anchor="end" dominant-baseline="middle">${frappe.utils.escape_html(
					tender_label_text
			  )}</text>`
			: "";

	const svg = `
		<svg class="ptpm-chart-svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}"
			preserveAspectRatio="xMinYMin meet" role="img" aria-label="${__(
				"Kitchen unit cost vs tender"
			)}">
			${grid_svg}
			${tender_line_svg}
			${bars_svg}
			${tender_label_svg}
			<g class="ptpm-chart-hover-layer"></g>
		</svg>`;

	const $canvas = $dash.find(".ptpm-chart-canvas");
	let $tooltip = $dash.find(".ptpm-chart-tooltip");
	if (!$tooltip.length) {
		$dash.find(".ptpm-chart-wrap").append('<div class="ptpm-chart-tooltip"></div>');
		$tooltip = $dash.find(".ptpm-chart-tooltip");
	}
	$canvas.html(svg);

	ptpm_bind_chart_hover($canvas, $tooltip, units, {
		pad,
		slot_w,
		chart_h,
		height,
		y_scale,
		tender_price: ptpm_get_chart_tender_price(site_ctx, units),
	});
}

function ptpm_position_chart_tooltip($tooltip, e) {
	const offset = 10;
	$tooltip.show();

	const tip_w = $tooltip.outerWidth() || 240;
	const tip_h = $tooltip.outerHeight() || 160;
	const max_left = window.innerWidth - tip_w - 8;
	const max_top = window.innerHeight - tip_h - 8;

	let left = e.clientX + offset;
	let top = e.clientY + offset;

	if (left > max_left) {
		left = e.clientX - tip_w - offset;
	}
	if (top > max_top) {
		top = e.clientY - tip_h - offset;
	}

	left = Math.max(8, Math.min(left, max_left));
	top = Math.max(8, Math.min(top, max_top));

	$tooltip.css({ left, top });
}

function ptpm_bind_chart_hover($canvas, $tooltip, units, layout) {
	const { pad, slot_w, chart_h, height, y_scale, tender_price: site_tender_price } = layout;

	$canvas.off("mousemove.ptpm-chart mouseleave.ptpm-chart");

	$canvas.on("mousemove.ptpm-chart", "svg", function (e) {
		const svgEl = this;
		const rect = svgEl.getBoundingClientRect();
		const view_w = svgEl.viewBox.baseVal.width || rect.width;
		const x = ((e.clientX - rect.left) / rect.width) * view_w;
		const idx = Math.floor((x - pad.left) / slot_w);

		if (idx < 0 || idx >= units.length) {
			ptpm_hide_chart_hover($canvas, $tooltip);
			return;
		}

		const unit = units[idx];
		const cx = pad.left + slot_w * idx + slot_w / 2;
		const tender_price = flt(site_tender_price);
		const cutoff_y = y_scale(tender_price);
		const total_cost = ptpm_unit_total_cost(unit);
		const profit_margin = ptpm_unit_profit_margin(unit);
		const margin_cls = ptpm_profit_margin_tooltip_class(profit_margin);

		let segments_html = "";
		unit.segments.forEach((seg) => {
			if (!seg.value) {
				return;
			}
			segments_html += `
				<div class="ptpm-chart-tooltip-row">
					<span>${seg.label}</span><strong>${ptpm_format_currency(seg.value)}</strong>
				</div>`;
		});

		$tooltip.html(`
			<div class="ptpm-chart-tooltip-title">${frappe.utils.escape_html(unit.label)}</div>
			<div class="ptpm-chart-tooltip-meta">${__("Site")}: ${frappe.utils.escape_html(unit.site_name)}</div>
			<div class="ptpm-chart-tooltip-meta">${__("Tender")}: ${frappe.utils.escape_html(unit.tender_name)}</div>
			<div class="ptpm-chart-tooltip-divider"></div>
			<div class="ptpm-chart-tooltip-row ptpm-chart-tooltip-row--tender">
				<span>${__("Tender Price Per Kitchen")}</span><strong>${ptpm_format_currency(tender_price)}</strong>
			</div>
			${segments_html}
			<div class="ptpm-chart-tooltip-divider"></div>
			<div class="ptpm-chart-tooltip-row">
				<span>${__("Total Cost")}</span><strong>${ptpm_format_currency(total_cost)}</strong>
			</div>
			<div class="ptpm-chart-tooltip-row ${margin_cls}">
				<span>${__("Profit Margin")}</span><strong>${ptpm_format_currency(profit_margin)}</strong>
			</div>
			<div class="ptpm-chart-tooltip-row ${margin_cls}">
				<span>${__("Margin %")}</span><strong>${unit.margin_pct.toFixed(2)}%</strong>
			</div>
		`);
		ptpm_position_chart_tooltip($tooltip, e);

		const hover_layer = svgEl.querySelector(".ptpm-chart-hover-layer");
		if (hover_layer) {
			hover_layer.innerHTML = `
				<line class="ptpm-chart-hover-line"
					x1="${cx}" y1="${pad.top}" x2="${cx}" y2="${pad.top + chart_h}" />
				<circle class="ptpm-chart-hover-cutoff" cx="${cx}" cy="${cutoff_y}" r="4" />
			`;
		}
	});

	$canvas.on("mouseleave.ptpm-chart", "svg", function () {
		ptpm_hide_chart_hover($canvas, $tooltip);
	});

	$canvas.closest(".ptpm-chart-wrap").off("mouseleave.ptpm-chart").on("mouseleave.ptpm-chart", function () {
		ptpm_hide_chart_hover($canvas, $tooltip);
	});
}

function ptpm_hide_chart_hover($canvas, $tooltip) {
	$tooltip.hide();
	$canvas.find(".ptpm-chart-hover-layer").empty();
}
