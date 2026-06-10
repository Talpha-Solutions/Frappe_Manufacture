// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const ASTPM_REPORT_NAME = "All Sites Tender Profit Margin";

const ASTPM_COST_SEGMENTS = [
	{ key: "manufacturing_actual_cost", label: __("Manufacturing Actual"), color: "#5dade2" },
	{ key: "task_actual_cost", label: __("Task Cost"), color: "#48c9b0" },
	{ key: "total_expense_claim", label: __("Expense Claims"), color: "#af7ac5" },
	{ key: "total_purchase_cost", label: __("Purchase Cost"), color: "#58d68d" },
	{ key: "total_consumed_material_cost", label: __("Material Cost"), color: "#f5b041" },
];

function astpm_is_report(report) {
	if (report?.report_name) {
		return report.report_name === ASTPM_REPORT_NAME;
	}
	const route = frappe.get_route();
	if (route[0] === "query-report") {
		return route[1] === ASTPM_REPORT_NAME;
	}
	return frappe.query_report?.report_name === ASTPM_REPORT_NAME;
}

function astpm_teardown() {
	$(".astpm-dashboard").remove();
}

if (!window._astpm_route_teardown_registered) {
	window._astpm_route_teardown_registered = true;
	frappe.router.on("change", () => {
		const route = frappe.get_route();
		if (route[0] !== "query-report" || route[1] !== ASTPM_REPORT_NAME) {
			astpm_teardown();
		}
	});
}

frappe.query_reports[ASTPM_REPORT_NAME] = {
	filters: [
		{
			label: __("Company"),
			fieldname: "company",
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
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
			label: __("Tender Configuration"),
			fieldname: "tender_configuration",
			fieldtype: "Link",
			options: "Tender Configuration",
		},
		{
			label: __("Work Order Status"),
			fieldname: "status",
			fieldtype: "Select",
			options: ["", "Not Started", "In Process", "Completed", "Stopped", "Closed"],
		},
	],

	onload() {
		astpm_inject_styles();
		astpm_hide_default_chrome();
	},

	after_refresh() {
		if (!astpm_is_report()) {
			return;
		}
		astpm_hide_default_chrome();
		astpm_render_dashboard();
	},

	get_chart_data() {
		return null;
	},

	after_datatable_render() {
		if (!astpm_is_report()) {
			return;
		}
		astpm_render_dashboard();
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

function astpm_inject_styles() {
	if (document.getElementById("astpm-report-styles-v7")) {
		return;
	}
	frappe.dom.set_style(`
		.astpm-dashboard { margin-bottom: 16px; }
		.astpm-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; padding: 16px 0; }
		@media (max-width: 1100px) { .astpm-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
		@media (max-width: 640px) { .astpm-kpi-grid { grid-template-columns: 1fr; } }
		.astpm-kpi-card { border-radius: 10px; padding: 14px 16px; min-height: 96px; display: flex; flex-direction: column; justify-content: space-between; border: 1px solid rgba(0,0,0,0.04); }
		.astpm-kpi-card--grey { background: #f4f6f8; }
		.astpm-kpi-card--green { background: #eafaf1; }
		.astpm-kpi-card--red { background: #fdecea; }
		.astpm-kpi-card--orange { background: #fef5e7; }
		.astpm-kpi-label { font-size: 11px; font-weight: 600; color: #6c7a89; line-height: 1.3; }
		.astpm-kpi-value { font-size: 28px; font-weight: 800; line-height: 1.1; margin: 6px 0; color: #1f272e; }
		.astpm-kpi-value--green { color: #1e8449; }
		.astpm-kpi-value--red { color: #c0392b; }
		.astpm-kpi-value--orange { color: #d68910; }
		.astpm-kpi-foot { font-size: 11px; color: #8d99a6; line-height: 1.35; }
		.astpm-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; padding: 10px 0 14px; border-bottom: 1px solid #eef0f3; font-size: 11px; color: #5a6773; }
		.astpm-legend-item { display: inline-flex; align-items: center; gap: 6px; }
		.astpm-legend-swatch { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
		.astpm-legend-cutoff { margin-left: auto; color: #c0392b; font-weight: 600; white-space: nowrap; }
		.astpm-chart-panel { border: 1px solid #e8eaed; border-radius: 10px; padding: 16px 16px 8px; margin-top: 4px; background: #fff; }
		.astpm-chart-title { font-size: 14px; font-weight: 700; color: #1f272e; margin: 0; }
		.astpm-chart-sub { font-size: 11px; color: #8d99a6; margin-top: 4px; margin-bottom: 12px; }
		.astpm-chart-wrap { width: 100%; overflow-x: auto; position: relative; }
		.astpm-chart-canvas svg { cursor: crosshair; }
		.astpm-chart-tooltip { position: fixed; display: none; min-width: 220px; max-width: 320px; padding: 10px 12px; background: #1f272e; color: #fff; border-radius: 8px; font-size: 11px; line-height: 1.45; box-shadow: 0 4px 16px rgba(0,0,0,0.18); pointer-events: none; z-index: 9999; }
		.astpm-chart-tooltip-title { font-size: 12px; font-weight: 700; margin-bottom: 6px; color: #fff; }
		.astpm-chart-tooltip-row { display: flex; justify-content: space-between; gap: 12px; margin-top: 3px; }
		.astpm-chart-tooltip-row strong { font-weight: 700; color: #fff; }
		.astpm-chart-tooltip-row--tender strong { color: #f1948a; }
		.astpm-chart-tooltip-row--profit strong { color: #58d68d; }
		.astpm-chart-tooltip-row--loss strong { color: #f1948a; }
		.astpm-chart-tooltip-divider { border-top: 1px solid rgba(255,255,255,0.15); margin: 8px 0 6px; }
		.astpm-chart-tooltip-meta { color: #d1d8dd; margin-top: 2px; }
		.astpm-chart-hover-line { stroke: #aeb6bf; stroke-width: 1; stroke-dasharray: 3 3; pointer-events: none; }
		.astpm-chart-hover-cutoff { fill: #e74c3c; stroke: #fff; stroke-width: 1.5; pointer-events: none; }
		.astpm-chart-svg { display: block; min-width: 640px; }
		.astpm-chart-axis { stroke: #e8eaed; stroke-width: 1; }
		.astpm-chart-cutoff-line { stroke: #e74c3c; stroke-width: 2; stroke-dasharray: 6 4; fill: none; pointer-events: none; }
		.astpm-chart-tender-bar { pointer-events: none; }
		.astpm-chart-cutoff-label { fill: #e74c3c; font-size: 10px; font-weight: 600; pointer-events: none; }
		.astpm-chart-seg-label { fill: #fff; font-size: 10px; font-weight: 700; text-anchor: middle; pointer-events: none; }
		.astpm-chart-margin-label { font-size: 11px; font-weight: 700; text-anchor: middle; pointer-events: none; }
		.astpm-chart-margin-label--profit { fill: #27ae60; }
		.astpm-chart-margin-label--loss { fill: #c0392b; }
		.astpm-chart-x-label { fill: #8d99a6; font-size: 10px; font-weight: 600; text-anchor: middle; }
		.astpm-chart-x-label--sub { fill: #aeb6bf; font-size: 9px; font-weight: 600; text-anchor: middle; }
		.astpm-chart-x-label--rotated { text-anchor: end; }
		.astpm-chart-y-label { fill: #aeb6bf; font-size: 10px; text-anchor: end; }
		.astpm-table-heading { font-size: 13px; font-weight: 700; color: #1f272e; padding: 18px 0 8px; border-top: 1px solid #eef0f3; margin-top: 8px; }
	`, "astpm-report-styles-v10");
}

function astpm_hide_default_chrome() {
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

function astpm_get_report_rows() {
	const result =
		frappe.query_report?.raw_data?.result || frappe.query_report?.data || [];
	return (result || []).filter(
		(row) =>
			row &&
			!row.is_total_row &&
			row.site &&
			String(row.site).trim() &&
			row.site !== __("Total")
	);
}

function astpm_compute_total_cost(row) {
	return ASTPM_COST_SEGMENTS.reduce((sum, seg) => sum + flt(row?.[seg.key]), 0);
}

function astpm_site_profit_margin(site) {
	return flt(site.profit_margin ?? site.row?.profit_margin);
}

function astpm_site_total_cost(site) {
	const segment_total = site.segments.reduce((sum, seg) => sum + flt(seg.value), 0);
	const row_total = flt(site.row?.total_cost);
	return row_total || segment_total;
}

function astpm_chart_y_scale(pad, chart_h, y_bottom, y_range) {
	return (val) => pad.top + chart_h - ((flt(val) - y_bottom) / y_range) * chart_h;
}

function astpm_profit_margin_bar_class(margin_pct) {
	return flt(margin_pct) >= 0 ? "astpm-chart-margin-label--profit" : "astpm-chart-margin-label--loss";
}

function astpm_profit_margin_tooltip_class(margin) {
	return flt(margin) >= 0 ? "astpm-chart-tooltip-row--profit" : "astpm-chart-tooltip-row--loss";
}

function astpm_unit_margin_pct(site) {
	return flt(site.margin_pct ?? site.row?.margin_pct);
}

function astpm_all_kitchens_completed(site) {
	return cint(site.all_kitchens_completed ?? site.row?.all_kitchens_completed) === 1;
}

function astpm_format_chart_bar_margin_pct(value) {
	return `${Math.round(flt(value))}%`;
}

function astpm_format_currency(value) {
	const currency =
		frappe.query_report?.columns?.find((col) => col.fieldtype === "Currency")?.options ||
		frappe.defaults.get_default("currency");
	return format_currency(flt(value), currency);
}

function astpm_chart_axis_label(row) {
	const code = (row.site || "").trim();
	const name = (row.site_name || "").trim();
	if (name && name.length <= 18) {
		return name;
	}
	if (code.length <= 14) {
		return code;
	}
	return code.split("-").slice(-2).join("-") || code;
}

function astpm_estimate_label_width(text, font_size = 10) {
	return Math.max(28, (text || "").length * (font_size * 0.62));
}

function astpm_split_label(label, max_width = 72) {
	const text = (label || "").trim();
	if (!text) {
		return { line1: "", line2: "", mode: "single" };
	}
	const max_chars = Math.max(8, Math.floor(max_width / 6.2));
	if (text.length <= max_chars) {
		return { line1: text, line2: "", mode: "single" };
	}
	const words = text.split(/\s+/);
	if (words.length > 1) {
		let line1 = words[0];
		for (let i = 1; i < words.length; i += 1) {
			const candidate = `${line1} ${words[i]}`;
			if (candidate.length <= max_chars) {
				line1 = candidate;
			} else {
				return { line1, line2: words.slice(i).join(" "), mode: "double" };
			}
		}
	}
	const mid = Math.ceil(text.length / 2);
	return { line1: text.slice(0, mid), line2: text.slice(mid), mode: "double" };
}

function astpm_render_x_axis_label(cx, base_y, label, layout) {
	const { slot_w, rotate_labels } = layout;
	const safe = frappe.utils.escape_html(label);
	if (rotate_labels) {
		return `<text class="astpm-chart-x-label astpm-chart-x-label--rotated" x="${cx}" y="${base_y}" transform="rotate(-42, ${cx}, ${base_y})" text-anchor="end">${safe}</text>`;
	}
	const { line1, line2, mode } = astpm_split_label(label, slot_w - 8);
	const safe1 = frappe.utils.escape_html(line1);
	const safe2 = frappe.utils.escape_html(line2);
	if (mode === "double" && line2) {
		return `
			<text class="astpm-chart-x-label" x="${cx}" y="${base_y - 12}" text-anchor="middle">${safe1}</text>
			<text class="astpm-chart-x-label astpm-chart-x-label--sub" x="${cx}" y="${base_y + 1}" text-anchor="middle">${safe2}</text>`;
	}
	return `<text class="astpm-chart-x-label" x="${cx}" y="${base_y - 4}" text-anchor="middle">${safe1}</text>`;
}

function astpm_collect_chart_data(rows) {
	return (rows || []).map((row) => {
		const segments = ASTPM_COST_SEGMENTS.map((seg) => ({
			...seg,
			value: flt(row[seg.key]),
		}));
		const total_cost = astpm_compute_total_cost(row) || flt(row.total_cost);
		const total_tender_budget = flt(row.total_tender_budget);
		const tender_price = flt(row.tender_price);

		return {
			label: row.site_name || row.site,
			axis_label: astpm_chart_axis_label(row),
			site: row.site,
			tender_name: row.tender_name || row.tender_configuration,
			total_cost,
			tender_price,
			total_tender_budget,
			tender_price_per_kitchen: flt(row.tender_price_per_kitchen),
			kitchen_count: cint(row.kitchen_count),
			profit_margin: flt(row.profit_margin),
			margin_pct: flt(row.margin_pct),
			over_tender: total_cost > total_tender_budget,
			segments,
			row,
		};
	});
}

function astpm_collect_kpi_data(sites) {
	const delayed_sites = sites
		.filter((site) => cint(site.row.is_site_delayed))
		.map((site) => ({ site: site.site, site_name: site.label }));
	const over_sites = sites.filter((site) => site.over_tender);
	const margin_pcts = sites.map((site) => site.margin_pct);
	const margins = sites.map((site) => site.profit_margin);
	const avg_margin_pct = margin_pcts.length
		? margin_pcts.reduce((sum, pct) => sum + pct, 0) / margin_pcts.length
		: 0;
	const avg_profit_margin = margins.length
		? margins.reduce((sum, margin) => sum + margin, 0) / margins.length
		: 0;

	return {
		site_count: sites.length,
		kitchen_count: sites.reduce((sum, site) => sum + site.kitchen_count, 0),
		delayed_sites,
		delayed_count: delayed_sites.length,
		over_sites,
		over_count: over_sites.length,
		avg_margin_pct,
		avg_profit_margin,
	};
}

function astpm_margin_status(avg_margin_pct) {
	if (avg_margin_pct < 0) {
		return __("below tender on average");
	}
	if (avg_margin_pct >= 15) {
		return __("healthy margin across sites");
	}
	return __("margin headroom available");
}

function astpm_margin_value_class(avg_margin_pct) {
	if (avg_margin_pct < 0) {
		return "astpm-kpi-value--red";
	}
	if (avg_margin_pct >= 15) {
		return "astpm-kpi-value--green";
	}
	return "astpm-kpi-value--orange";
}

function astpm_over_tender_foot(over_sites) {
	if (!over_sites.length) {
		return __("all sites within tender budget");
	}
	const labels = over_sites.slice(0, 2).map((site) => site.axis_label || site.label);
	let foot = labels.join(", ");
	if (over_sites.length > 2) {
		foot += ` +${over_sites.length - 2}`;
	}
	return `${foot} · ${__("review cost overrun")}`;
}

function astpm_delayed_foot(delayed_sites) {
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

function astpm_site_tender_price(site) {
	return flt(
		site.tender_price ??
			site.total_tender_budget ??
			site.row?.tender_price ??
			site.row?.total_tender_budget
	);
}

function astpm_slot_bar_layout(slot_w) {
	const pair_gap = 6;
	const max_pair_w = Math.max(slot_w - 8, 16);
	const bar_w = Math.max(10, Math.min(28, (max_pair_w - pair_gap) / 2));
	return { bar_w, pair_gap };
}

function astpm_render_tender_price_bar_svg(cx, bar_w, tender_price, y_scale) {
	const tender_val = flt(tender_price);
	const baseline_y = y_scale(0);
	if (tender_val <= 0) {
		return { svg: "", top_y: baseline_y, marker_y: baseline_y };
	}

	const top_y = y_scale(tender_val);
	const bar_h = baseline_y - top_y;
	if (bar_h < 1) {
		return { svg: "", top_y: baseline_y, marker_y: baseline_y };
	}

	let svg = `<rect class="astpm-chart-tender-bar" x="${cx - bar_w / 2}" y="${top_y}" width="${bar_w}" height="${bar_h}" fill="#f1948a" stroke="#e74c3c" stroke-width="1.5" rx="2"></rect>`;
	if (bar_h >= 14) {
		svg += `<text class="astpm-chart-seg-label" x="${cx}" y="${top_y + bar_h / 2 + 4}">${Math.round(
			tender_val
		)}</text>`;
	}

	return { svg, top_y, marker_y: top_y };
}

function astpm_chart_layout(sites) {
	const axis_labels = sites.map((site) => site.axis_label || site.label);
	const max_label_width = Math.max(...axis_labels.map((label) => astpm_estimate_label_width(label)), 48);
	const period_count = sites.length;
	const slot_min = Math.max(period_count > 10 ? 72 : 96, Math.ceil(max_label_width + 16));
	const width = Math.max(640, period_count * slot_min + 80);
	const pad = { top: 28, right: 24, left: 36 };
	const chart_w = width - pad.left - pad.right;
	const slot_w = Math.max(chart_w / period_count, 1);
	const rotate_labels = slot_w < max_label_width + 8;
	pad.bottom = rotate_labels ? 78 : 52;
	const height = rotate_labels ? 334 : 310;
	const chart_h = height - pad.top - pad.bottom;

	return { width, height, pad, chart_w, chart_h, slot_w, rotate_labels };
}

function astpm_render_kpi_cards($dash, kpi) {
	const cards = [
		{
			cls: "astpm-kpi-card--grey",
			label: __("Sites with tender"),
			value: kpi.site_count,
			value_cls: "",
			foot: `${kpi.kitchen_count} ${__("child projects")}`,
		},
		{
			cls: "astpm-kpi-card--green",
			label: __("Avg margin %"),
			value: `${Math.round(kpi.avg_margin_pct)}%`,
			value_cls: astpm_margin_value_class(kpi.avg_margin_pct),
			foot: astpm_margin_status(kpi.avg_margin_pct),
		},
		{
			cls: "astpm-kpi-card--red",
			label: __("Sites over tender"),
			value: kpi.over_count,
			value_cls: kpi.over_count > 0 ? "astpm-kpi-value--red" : "",
			foot: astpm_over_tender_foot(kpi.over_sites),
		},
		{
			cls: "astpm-kpi-card--orange",
			label: __("Delayed projects"),
			value: kpi.delayed_count,
			value_cls: kpi.delayed_count > 0 ? "astpm-kpi-value--red" : "",
			foot: astpm_delayed_foot(kpi.delayed_sites),
		},
	];

	$dash.find(".astpm-kpi-grid").html(
		cards
			.map(
				(card) => `
		<div class="astpm-kpi-card ${card.cls}">
			<div class="astpm-kpi-label">${card.label}</div>
			<div class="astpm-kpi-value ${card.value_cls}">${card.value}</div>
			<div class="astpm-kpi-foot">${card.foot}</div>
		</div>`
			)
			.join("")
	);
}

function astpm_render_legend($dash) {
	const segment_legend = ASTPM_COST_SEGMENTS.map(
		(seg) => `
		<span class="astpm-legend-item">
			<span class="astpm-legend-swatch" style="background:${seg.color}"></span>
			<span>${seg.label}</span>
		</span>`
	).join("");

	$dash.find(".astpm-legend").html(`
		${segment_legend}
		<span class="astpm-legend-item">
			<span class="astpm-legend-swatch" style="background:#f1948a;border:1px solid #e74c3c"></span>
			<span>${__("Tender Price")}</span>
		</span>
	`);
}

function astpm_render_empty_chart($dash, message) {
	$dash.find(".astpm-chart-canvas").html(
		`<div style="padding:40px;text-align:center;color:#8d99a6">${message}</div>`
	);
}

function astpm_render_chart($dash, sites) {
	if (!sites.length) {
		astpm_render_empty_chart(
			$dash,
			__("No Site projects found for the selected company")
		);
		return;
	}

	const layout = astpm_chart_layout(sites);
	let { width, height, pad, chart_h, slot_w } = layout;
	const { bar_w, pair_gap } = astpm_slot_bar_layout(slot_w);

	const max_cost = Math.max(...sites.map((site) => astpm_site_total_cost(site)), 0);
	const max_tender = Math.max(...sites.map((site) => astpm_site_tender_price(site)), 0);
	const y_top = Math.max(max_cost, max_tender, 1);
	const y_bottom = 0;
	const y_range = y_top - y_bottom || 1;
	const y_scale = astpm_chart_y_scale(pad, chart_h, y_bottom, y_range);
	const baseline_y = y_scale(0);

	let bars_svg = "";
	const tender_bar_positions = [];

	sites.forEach((site, idx) => {
		const cx = pad.left + slot_w * idx + slot_w / 2;
		const cost_cx = cx - (bar_w + pair_gap) / 2;
		const tender_cx = cx + (bar_w + pair_gap) / 2;
		let y_cursor = pad.top + chart_h;
		const total_cost = astpm_site_total_cost(site);
		const stack_total = site.segments.reduce((sum, seg) => sum + seg.value, 0);
		const bar_total = total_cost > 0 ? total_cost : stack_total;
		const tender_price = astpm_site_tender_price(site);
		let chart_top_y = baseline_y;

		site.segments.forEach((seg) => {
			if (!seg.value) {
				return;
			}
			const share = stack_total > 0 ? seg.value / stack_total : 0;
			const seg_val = bar_total * share;
			const seg_h = (seg_val / y_range) * chart_h;
			if (seg_h <= 0) {
				return;
			}
			const y = y_cursor - seg_h;
			bars_svg += `<rect x="${cost_cx - bar_w / 2}" y="${y}" width="${bar_w}" height="${seg_h}" fill="${seg.color}" rx="2"></rect>`;
			if (seg_h >= 12 && seg.value > 0) {
				bars_svg += `<text class="astpm-chart-seg-label" x="${cost_cx}" y="${y + seg_h / 2 + 4}">${Math.round(
					seg.value
				)}</text>`;
			}
			y_cursor = y;
			chart_top_y = Math.min(chart_top_y, y);
		});

		let tender_marker_y = baseline_y;
		if (tender_price > 0) {
			const tender_bar = astpm_render_tender_price_bar_svg(tender_cx, bar_w, tender_price, y_scale);
			bars_svg += tender_bar.svg;
			if (tender_bar.top_y !== undefined) {
				chart_top_y = Math.min(chart_top_y, tender_bar.top_y);
			}
			tender_marker_y = tender_bar.marker_y ?? baseline_y;
		}

		if (
			astpm_all_kitchens_completed(site) &&
			(total_cost > 0 || tender_price > 0 || Math.abs(astpm_site_profit_margin(site)) > 0.001)
		) {
			const margin_pct = astpm_unit_margin_pct(site);
			const margin_cls = astpm_profit_margin_bar_class(margin_pct);
			const label_y = chart_top_y - 3;
			bars_svg += `<text class="astpm-chart-margin-label ${margin_cls}" x="${cx}" y="${label_y}">${astpm_format_chart_bar_margin_pct(
				margin_pct
			)}</text>`;
		}

		tender_bar_positions.push({ cx, tender_cx, tender_marker_y });

		bars_svg += astpm_render_x_axis_label(cx, height - 10, site.axis_label || site.label, layout);
	});

	let grid_svg = "";
	const y_ticks = 5;
	for (let i = 0; i <= y_ticks; i += 1) {
		const val = Math.round(y_bottom + (y_range / y_ticks) * i);
		const y = y_scale(val);
		grid_svg += `<line class="astpm-chart-axis" x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" />`;
		grid_svg += `<text class="astpm-chart-y-label" x="${pad.left - 6}" y="${y + 4}">${val}</text>`;
	}

	const svg = `
		<svg class="astpm-chart-svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}"
			preserveAspectRatio="xMinYMin meet" role="img" aria-label="${__("Site cost vs tender budget")}">
			${grid_svg}
			${bars_svg}
			<g class="astpm-chart-hover-layer"></g>
		</svg>`;

	const $canvas = $dash.find(".astpm-chart-canvas");
	let $tooltip = $dash.find(".astpm-chart-tooltip");
	if (!$tooltip.length) {
		$dash.find(".astpm-chart-wrap").append('<div class="astpm-chart-tooltip"></div>');
		$tooltip = $dash.find(".astpm-chart-tooltip");
	}
	$canvas.html(svg);

	astpm_bind_chart_hover($canvas, $tooltip, sites, {
		pad,
		slot_w,
		chart_h,
		height,
		y_scale,
		tender_bar_positions,
	});
}

function astpm_position_chart_tooltip($tooltip, e) {
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
	$tooltip.css({ left: Math.max(8, Math.min(left, max_left)), top: Math.max(8, Math.min(top, max_top)) });
}

function astpm_bind_chart_hover($canvas, $tooltip, sites, layout) {
	const { pad, slot_w, chart_h, tender_bar_positions } = layout;

	$canvas.off("mousemove.astpm-chart mouseleave.astpm-chart");
	$canvas.on("mousemove.astpm-chart", "svg", function (e) {
		const svgEl = this;
		const rect = svgEl.getBoundingClientRect();
		const view_w = svgEl.viewBox.baseVal.width || rect.width;
		const x = ((e.clientX - rect.left) / rect.width) * view_w;
		const idx = Math.floor((x - pad.left) / slot_w);

		if (idx < 0 || idx >= sites.length) {
			$tooltip.hide();
			svgEl.querySelector(".astpm-chart-hover-layer")?.replaceChildren();
			return;
		}

		const site = sites[idx];
		const bar_pos = tender_bar_positions?.[idx] || {};
		const cx = bar_pos.cx ?? pad.left + slot_w * idx + slot_w / 2;
		const tender_cx = bar_pos.tender_cx ?? cx;
		const total_cost = astpm_site_total_cost(site);
		const profit_margin = astpm_site_profit_margin(site);
		const margin_cls = astpm_profit_margin_tooltip_class(profit_margin);
		const tender_budget = astpm_site_tender_price(site);
		const tender_marker_y = bar_pos.tender_marker_y ?? pad.top + chart_h;

		let segments_html = "";
		site.segments.forEach((seg) => {
			if (!seg.value) {
				return;
			}
			segments_html += `
				<div class="astpm-chart-tooltip-row">
					<span>${seg.label}</span><strong>${astpm_format_currency(seg.value)}</strong>
				</div>`;
		});

		$tooltip.html(`
			<div class="astpm-chart-tooltip-title">${frappe.utils.escape_html(site.label)}</div>
			<div class="astpm-chart-tooltip-meta">${frappe.utils.escape_html(site.site)} · ${site.kitchen_count} ${__(
				"child projects"
			)}</div>
			<div class="astpm-chart-tooltip-meta">${__("Tender")}: ${frappe.utils.escape_html(site.tender_name || "—")}</div>
			<div class="astpm-chart-tooltip-divider"></div>
			<div class="astpm-chart-tooltip-row astpm-chart-tooltip-row--tender">
				<span>${__("Tender Price")}</span><strong>${astpm_format_currency(tender_budget)}</strong>
			</div>
			<div class="astpm-chart-tooltip-row">
				<span>${__("Tender Price Per Kitchen")}</span><strong>${astpm_format_currency(
					site.tender_price_per_kitchen
				)}</strong>
			</div>
			${segments_html}
			<div class="astpm-chart-tooltip-divider"></div>
			<div class="astpm-chart-tooltip-row">
				<span>${__("Total Cost")}</span><strong>${astpm_format_currency(total_cost)}</strong>
			</div>
			<div class="astpm-chart-tooltip-row ${margin_cls}">
				<span>${__("Profit Margin")}</span><strong>${astpm_format_currency(profit_margin)}</strong>
			</div>
			<div class="astpm-chart-tooltip-row ${margin_cls}">
				<span>${__("Margin %")}</span><strong>${site.margin_pct.toFixed(2)}%</strong>
			</div>
		`);
		astpm_position_chart_tooltip($tooltip, e);

		const hover_layer = svgEl.querySelector(".astpm-chart-hover-layer");
		if (hover_layer) {
			hover_layer.innerHTML = `
				<line class="astpm-chart-hover-line" x1="${cx}" y1="${pad.top}" x2="${cx}" y2="${pad.top + chart_h}" />
				<circle class="astpm-chart-hover-cutoff" cx="${tender_cx}" cy="${tender_marker_y}" r="4" />
			`;
		}
	});

	$canvas.on("mouseleave.astpm-chart", "svg", function () {
		$tooltip.hide();
		this.querySelector(".astpm-chart-hover-layer")?.replaceChildren();
	});
}

let astpm_render_token = 0;

function astpm_render_dashboard() {
	const render_token = ++astpm_render_token;
	astpm_teardown();
	astpm_hide_default_chrome();

	const rows = astpm_get_report_rows();
	const $target = $(".report-wrapper").first();
	if (!$target.length) {
		return;
	}

	const from_date = frappe.query_report.get_filter_value("from_date");
	const to_date = frappe.query_report.get_filter_value("to_date");
	const from_label = from_date ? frappe.datetime.str_to_user(from_date) : "";
	const to_label = to_date ? frappe.datetime.str_to_user(to_date) : "";

	const dashboard = $(`
		<div class="astpm-dashboard">
			<div class="astpm-kpi-grid"></div>
			<div class="astpm-legend"></div>
			<div class="astpm-chart-panel">
				<div class="astpm-chart-title">${__("All Sites Cost vs Tender Budget")}</div>
				<div class="astpm-chart-sub">${__(
					"One bar per Site project — with or without linked tender"
				)} · ${from_label} — ${to_label}</div>
				<div class="astpm-chart-wrap">
					<div class="astpm-chart-canvas"></div>
					<div class="astpm-chart-tooltip"></div>
				</div>
			</div>
			<div class="astpm-table-heading">${__("Detailed site breakdown")}</div>
		</div>
	`);

	$target.before(dashboard);
	if (render_token !== astpm_render_token) {
		dashboard.remove();
		return;
	}

	const sites = astpm_collect_chart_data(rows);
	const kpi = astpm_collect_kpi_data(sites);
	astpm_render_kpi_cards(dashboard, kpi);
	astpm_render_legend(dashboard);
	astpm_render_chart(dashboard, sites);
}
