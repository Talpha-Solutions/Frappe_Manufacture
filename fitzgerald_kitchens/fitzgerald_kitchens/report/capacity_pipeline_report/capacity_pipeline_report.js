// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const CPR_PALETTE = [
	{ bg: "#d4e8f7", text: "#1a5276", chart: "#5dade2" },
	{ bg: "#e8d5f5", text: "#6c3483", chart: "#af7ac5" },
	{ bg: "#d5f5e3", text: "#1e8449", chart: "#58d68d" },
	{ bg: "#fdebd0", text: "#7d6608", chart: "#f5b041" },
	{ bg: "#fadbd8", text: "#922b21", chart: "#ec7063" },
	{ bg: "#d1f2eb", text: "#117a65", chart: "#48c9b0" },
	{ bg: "#e8daef", text: "#512e5f", chart: "#bb8fce" },
	{ bg: "#fcf3cf", text: "#7d6608", chart: "#f4d03f" },
];

const CPR_REPORT_NAME = "Capacity Pipeline Report";

let cpr_horizon_months = 12;
let cpr_view_mode = "monthly";
let cpr_last_pipeline_totals = null;
let cpr_pipeline_totals_filter_sig = "";

function cpr_is_capacity_pipeline_report(report) {
	if (report?.report_name) {
		return report.report_name === CPR_REPORT_NAME;
	}
	const route = frappe.get_route();
	if (route[0] === "query-report") {
		return route[1] === CPR_REPORT_NAME;
	}
	return frappe.query_report?.report_name === CPR_REPORT_NAME;
}

function cpr_teardown() {
	$(".cpr-header, .cpr-dashboard").remove();
	$(".layout-main-section").removeClass("cpr-page");
	$(".page-head").show();
	cpr_dashboard_render_seq += 1;
}

function cpr_register_route_teardown() {
	if (window._cpr_route_teardown_registered) {
		return;
	}
	window._cpr_route_teardown_registered = true;

	frappe.router.on("change", () => {
		const route = frappe.get_route();
		if (route[0] !== "query-report" || route[1] !== CPR_REPORT_NAME) {
			cpr_teardown();
		}
	});

	if (frappe.views?.QueryReport?.prototype && !window._cpr_load_report_hook) {
		window._cpr_load_report_hook = true;
		const original_load_report = frappe.views.QueryReport.prototype.load_report;
		frappe.views.QueryReport.prototype.load_report = function (route_options) {
			const next_report = frappe.get_route()[1];
			if (next_report !== CPR_REPORT_NAME) {
				cpr_teardown();
			}
			return original_load_report.call(this, route_options);
		};
	}
}

cpr_register_route_teardown();

frappe.query_reports[CPR_REPORT_NAME] = {
	filters: [
		{
			label: __("Company"),
			fieldname: "company",
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
			on_change: function () {
				frappe.query_report.set_filter_value("bom", "");
				cpr_set_default_bom(true);
			},
		},
		{
			label: __("From Date"),
			fieldname: "from_date",
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
			on_change: function () {
				cpr_apply_horizon(cpr_horizon_months);
			},
		},
		{
			label: __("To Date"),
			fieldname: "to_date",
			fieldtype: "Date",
			default: (() =>
				moment()
					.startOf("month")
					.add(11, "months")
					.endOf("month")
					.format("YYYY-MM-DD"))(),
			reqd: 1,
		},
		{
			label: __("BOM"),
			fieldname: "bom",
			fieldtype: "Link",
			options: "BOM",
			default: "",
			get_query: () => {
				const company = cpr_get_company();
				return {
					filters: {
						docstatus: 1,
						is_active: 1,
						...(company ? { company } : {}),
					},
				};
			},
		},
		{
			label: __("Project"),
			fieldname: "project",
			fieldtype: "Link",
			options: "Project",
		},
		{
			label: __("Granularity"),
			fieldname: "granularity",
			fieldtype: "Select",
			options: "Monthly\nWeekly",
			default: "Monthly",
			hidden: 1,
		},
	],

	onload(report) {
		cpr_register_route_teardown();
		if (!cpr_is_capacity_pipeline_report(report)) {
			return;
		}
		cpr_teardown();
		cpr_ensure_workspace_sidebar();
		cpr_inject_styles();
		cpr_setup_header(report);
		cpr_setup_dashboard(report);
		cpr_hide_default_chrome(report);
		return cpr_prepare_filters_before_refresh(report);
	},

	get_datatable_options(options) {
		if (!cpr_is_capacity_pipeline_report()) {
			return options;
		}
		const saved = cpr_get_saved_column_widths();
		if (options.columns?.length) {
			options.columns = options.columns.map((col) => {
				const key = col.fieldname || col.id;
				const width = saved[key] || col.width;
				return {
					...col,
					width: width ? parseInt(width, 10) : col.width,
					resizable: col.resizable !== false,
				};
			});
		}

		return Object.assign(options, {
			layout: "fixed",
			minimumColumnWidth: 48,
			cellHeight: 52,
			serialNoColumn: false,
			showTotalRow: false,
			dynamicRowHeight: true,
			scrollY: false,
		});
	},

	after_datatable_render() {
		if (!cpr_is_capacity_pipeline_report()) {
			return;
		}
		cpr_style_rows();
		cpr_bind_column_resize();
		cpr_fix_horizontal_scroll();
		cpr_update_header_bom();
		cpr_render_dashboard(frappe.query_report);
	},

	after_refresh(report) {
		if (!cpr_is_capacity_pipeline_report(report)) {
			return;
		}
		cpr_sync_bom_filter_from_boot(report);
		cpr_sync_view_mode_from_filters();
		cpr_apply_table_site_only_rows(report);
		cpr_sync_pipeline_totals_cache(report);
		cpr_render_dashboard(report);
	},

	formatter(value, row, column, data, default_formatter) {
		if (!cpr_is_capacity_pipeline_report()) {
			return default_formatter(value, row, column, data);
		}
		const row_data = cpr_get_row_data(row, data);
		const rt = cpr_get_row_type(row_data, value);
		const fn = column.fieldname;

		if (fn === "project") {
			return cpr_fmt_label(rt, value, row_data);
		}

		if (rt === "separator") {
			return `<div class="cpr-sep-cell"></div>`;
		}

		const num = cint(value);

		if (rt === "project") return cpr_fmt_project_cell(num, row_data, fn);
		if (rt === "downtime") return cpr_fmt_downtime_cell(num);
		if (rt === "capacity") return cpr_fmt_capacity_cell(value, fn, row_data);
		if (rt === "demand") return cpr_fmt_demand_cell(num, fn, row_data);
		if (rt === "free") return cpr_fmt_free_cell(num);

		return default_formatter(value, row, column, row_data);
	},
};

function cpr_get_row_data(row, data) {
	const full_row =
		(frappe.query_report?.data && frappe.query_report.data[row]) || {};

	// Datatable passes a sparse row object (column values only). Merge with the
	// full report row so metadata like m_2026_06_pct and row_type is available.
	if (data && typeof data === "object" && !Array.isArray(data)) {
		return { ...full_row, ...data };
	}

	return full_row;
}

function cpr_get_row_type(row_data, project_value) {
	if (row_data.row_type) {
		return row_data.row_type;
	}

	const label = (row_data.project || project_value || "").trim();
	if (!label || label === " ") {
		return "separator";
	}
	if (
		label === __("Capacity per month")
		|| label === "Capacity per month"
		|| label === __("Capacity / month")
		|| label === "Capacity / month"
		|| label === __("Capacity / week")
		|| label === "Capacity / week"
	) {
		return "capacity";
	}
	if (label.includes("Downtime") || label === __("Downtime (mins)")) {
		return "downtime";
	}
	if (label.includes("utilisation") || label.includes("utilization")) {
		return "demand";
	}
	if (label === __("Free capacity") || label === "Free capacity") {
		return "free";
	}
	return "project";
}

function cint(v) {
	if (v === null || v === undefined || v === "") {
		return 0;
	}
	return parseInt(v, 10) || 0;
}

function cpr_ensure_workspace_sidebar() {
	if (!frappe.app?.sidebar || !frappe.boot.workspace_sidebar_item?.projects) {
		return;
	}
	frappe.app.sidebar.setup("Projects");
	setTimeout(() => frappe.app.sidebar.set_active_workspace_item?.(), 0);
}

function cpr_inject_styles() {
	if (document.getElementById("cpr-report-styles")) return;

	const css = `
		.cpr-page .page-head { display: none !important; }
		.cpr-page .layout-main-section { background: #f4f5f7; padding: 0 16px 24px; }
		.cpr-header { background: #fff; border: 1px solid #e8eaed; border-bottom: none; border-radius: 8px 8px 0 0; padding: 20px 24px 14px; margin-top: 12px; }
		.cpr-header-title { font-size: 22px; font-weight: 700; color: #1f272e; line-height: 1.25; margin: 0; }
		.cpr-header-sub { font-size: 12px; color: #8d99a6; margin-top: 6px; line-height: 1.4; max-width: 720px; }
		.cpr-page .page-form { background: #fff; border-left: 1px solid #e8eaed; border-right: 1px solid #e8eaed; border-bottom: none; border-top: none; margin-top: 0; padding: 8px 16px 4px; }
		.cpr-dashboard { background: #fff; border-left: 1px solid #e8eaed; border-right: 1px solid #e8eaed; padding: 0 20px 20px; }
		.cpr-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 14px 0 18px; border-bottom: 1px solid #eef0f3; }
		.cpr-toggle-group { display: inline-flex; border: 1px solid #d1d8dd; border-radius: 6px; overflow: hidden; background: #fff; }
		.cpr-toggle-btn { border: none; background: #fff; color: #5a6773; font-size: 12px; font-weight: 600; padding: 6px 14px; cursor: pointer; line-height: 1.2; }
		.cpr-toggle-btn + .cpr-toggle-btn { border-left: 1px solid #d1d8dd; }
		.cpr-toggle-btn.is-active { background: #f0f4f7; color: #1f272e; box-shadow: inset 0 0 0 1px #c5d0db; }
		.cpr-toggle-btn.is-disabled { opacity: 0.45; cursor: not-allowed; }
		.cpr-controls-meta { flex: 1; font-size: 12px; color: #8d99a6; min-width: 220px; }
		.cpr-add-project { margin-left: auto; white-space: nowrap; }
		.cpr-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; padding: 16px 0; }
		@media (max-width: 1100px) { .cpr-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
		@media (max-width: 640px) { .cpr-kpi-grid { grid-template-columns: 1fr; } }
		.cpr-kpi-card { border-radius: 10px; padding: 14px 16px; min-height: 96px; display: flex; flex-direction: column; justify-content: space-between; border: 1px solid rgba(0,0,0,0.04); }
		.cpr-kpi-card--grey { background: #f4f6f8; }
		.cpr-kpi-card--green { background: #eafaf1; }
		.cpr-kpi-card--red { background: #fdecea; }
		.cpr-kpi-card--orange { background: #fef5e7; }
		.cpr-kpi-label { font-size: 11px; font-weight: 600; color: #6c7a89; line-height: 1.3; }
		.cpr-kpi-value { font-size: 28px; font-weight: 800; line-height: 1.1; margin: 6px 0; color: #1f272e; }
		.cpr-kpi-value--green { color: #1e8449; }
		.cpr-kpi-value--red { color: #c0392b; }
		.cpr-kpi-value--orange { color: #d68910; }
		.cpr-kpi-foot { font-size: 11px; color: #8d99a6; line-height: 1.35; }
		.cpr-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; padding: 10px 0 14px; border-bottom: 1px solid #eef0f3; font-size: 11px; color: #5a6773; }
		.cpr-legend-item { display: inline-flex; align-items: center; gap: 6px; }
		.cpr-legend-swatch { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
		.cpr-legend-capacity { margin-left: auto; color: #c0392b; font-weight: 600; white-space: nowrap; }
		.cpr-chart-panel { border: 1px solid #e8eaed; border-radius: 10px; padding: 16px 16px 8px; margin-top: 4px; background: #fff; }
		.cpr-chart-title { font-size: 14px; font-weight: 700; color: #1f272e; margin: 0; }
		.cpr-chart-sub { font-size: 11px; color: #8d99a6; margin-top: 4px; margin-bottom: 12px; }
		.cpr-chart-wrap { width: 100%; overflow-x: auto; position: relative; }
		.cpr-chart-canvas svg { cursor: crosshair; }
		.cpr-chart-tooltip {
			position: absolute;
			display: none;
			min-width: 180px;
			max-width: 280px;
			padding: 10px 12px;
			background: #1f272e;
			color: #fff;
			border-radius: 8px;
			font-size: 11px;
			line-height: 1.45;
			box-shadow: 0 4px 16px rgba(0,0,0,0.18);
			pointer-events: none;
			z-index: 6;
		}
		.cpr-chart-tooltip-title {
			font-size: 12px;
			font-weight: 700;
			margin-bottom: 6px;
			color: #fff;
		}
		.cpr-chart-tooltip-row { display: flex; justify-content: space-between; gap: 12px; margin-top: 3px; }
		.cpr-chart-tooltip-row strong { font-weight: 700; color: #fff; }
		.cpr-chart-tooltip-row--capacity strong { color: #f1948a; }
		.cpr-chart-tooltip-row--over strong { color: #f1948a; }
		.cpr-chart-tooltip-row--ok strong { color: #58d68d; }
		.cpr-chart-tooltip-divider {
			border-top: 1px solid rgba(255,255,255,0.15);
			margin: 8px 0 6px;
		}
		.cpr-chart-tooltip-project { color: #d1d8dd; margin-top: 2px; }
		.cpr-chart-hover-line { stroke: #aeb6bf; stroke-width: 1; stroke-dasharray: 3 3; pointer-events: none; }
		.cpr-chart-hover-cap { fill: #e74c3c; stroke: #fff; stroke-width: 1.5; pointer-events: none; }
		.cpr-chart-svg { display: block; min-width: 640px; }
		.cpr-chart-axis { stroke: #e8eaed; stroke-width: 1; }
		.cpr-chart-cap-line { stroke: #e74c3c; stroke-width: 1.5; stroke-dasharray: 6 4; fill: none; }
		.cpr-chart-cap-label { fill: #e74c3c; font-size: 10px; font-weight: 600; }
		.cpr-chart-seg-label {
			fill: #fff;
			font-size: 10px;
			font-weight: 700;
			text-anchor: middle;
			pointer-events: none;
		}
		.cpr-chart-total-label { fill: #1f272e; font-size: 11px; font-weight: 700; text-anchor: middle; }
		.cpr-chart-x-label { fill: #8d99a6; font-size: 10px; font-weight: 600; text-anchor: middle; }
		.cpr-chart-x-label--sub { fill: #aeb6bf; font-size: 9px; font-weight: 600; text-anchor: middle; }
		.cpr-chart-y-label { fill: #aeb6bf; font-size: 10px; text-anchor: end; }
		.cpr-table-heading { font-size: 13px; font-weight: 700; color: #1f272e; padding: 18px 0 8px; border-top: 1px solid #eef0f3; margin-top: 8px; }
		.cpr-page .report-wrapper { background: #fff; border: 1px solid #e8eaed; border-top: none; border-radius: 0 0 8px 8px; overflow-x: auto !important; overflow-y: hidden; padding: 0; margin-top: 0; width: 100%; }
		.cpr-page .report-wrapper .datatable { min-width: max-content; }
		.cpr-page .report-footer { display: none !important; }
		.cpr-page .dt-scrollable { overflow-x: auto !important; overflow-y: visible !important; width: 100% !important; }
		.cpr-page .dt-scrollable .dt-header,
		.cpr-page .dt-scrollable .dt-body { min-width: max-content !important; }
		.cpr-page .dt-header .dt-cell { font-size: 11px !important; font-weight: 600 !important; color: #8d99a6 !important; letter-spacing: 0.04em; text-transform: uppercase; border-bottom: 1px solid #e8eaed !important; background: #fff !important; }
		.cpr-page .dt-row .dt-cell { border-bottom: 1px solid #f0f2f5 !important; vertical-align: middle !important; }
		.cpr-page .dt-row .dt-cell:first-child,
		.cpr-page .dt-header .dt-cell:first-child { position: sticky; left: 0; z-index: 2; background: #fff; box-shadow: 2px 0 4px rgba(0,0,0,0.04); min-width: 180px; }
		.cpr-page .dt-header .dt-cell .dt-cell__resize-handle { opacity: 0.35; }
		.cpr-page .dt-header .dt-cell:hover .dt-cell__resize-handle { opacity: 1; }
		.cpr-page .dt-row.cpr-summary-row .dt-cell { background: #fafbfc !important; border-top: 1px solid #e8eaed !important; }
		.cpr-page .dt-row.cpr-summary-row .dt-cell:first-child { background: #fafbfc !important; }
		.cpr-page .dt-row.cpr-separator-row { height: 8px !important; }
		.cpr-page .dt-row.cpr-separator-row .dt-cell { padding: 0 !important; border-bottom: 1px solid #e8eaed !important; background: #fff !important; }
		.cpr-sep-cell { border-top: 1px solid #e8eaed; margin: 0; height: 1px; }
		.cpr-project-link { color: inherit; text-decoration: none; cursor: pointer; }
		.cpr-project-link:hover { color: var(--primary, #2490ef); text-decoration: underline; }
		.cpr-demand-badge { cursor: help; }
	`;

	$("<style>", { id: "cpr-report-styles", text: css }).appendTo("head");
}

function cpr_setup_header(report) {
	if (!cpr_is_capacity_pipeline_report(report)) {
		return;
	}
	const $main = report.page.main;
	$main.closest(".layout-main-section").addClass("cpr-page");

	if (!$main.find(".cpr-header").length) {
		const header = $(`
			<div class="cpr-header">
				<h4 class="cpr-header-title">${__("Kitchen capacity pipeline")}</h4>
				<div class="cpr-header-sub">${__(
					"Production load vs capacity across all projects · adjustable from weekly to 18-month horizon"
				)}</div>
				<div class="cpr-header-bom" style="display:none;font-size:11px;color:#5a6773;margin-top:4px"></div>
			</div>
		`);
		$main.find(".page-form").before(header);
	}
}

function cpr_setup_dashboard(report) {
	if (!cpr_is_capacity_pipeline_report(report)) {
		return;
	}
	const $main = report.page.main;
	if ($main.find(".cpr-dashboard").length) {
		return;
	}

	const dashboard = $(`
		<div class="cpr-dashboard">
			<div class="cpr-controls">
				<div class="cpr-toggle-group cpr-view-toggle">
					<button type="button" class="cpr-toggle-btn" data-view="weekly">${__("Weekly")}</button>
					<button type="button" class="cpr-toggle-btn is-active" data-view="monthly">${__("Monthly")}</button>
					<button type="button" class="cpr-toggle-btn" data-view="quarterly">${__("Quarterly")}</button>
				</div>
				<div class="cpr-toggle-group cpr-horizon-toggle">
					<button type="button" class="cpr-toggle-btn" data-months="3">3 ${__("mo")}</button>
					<button type="button" class="cpr-toggle-btn" data-months="6">6 ${__("mo")}</button>
					<button type="button" class="cpr-toggle-btn is-active" data-months="12">12 ${__("mo")}</button>
					<button type="button" class="cpr-toggle-btn" data-months="18">18 ${__("mo")}</button>
				</div>
				<div class="cpr-controls-meta"></div>
				<button type="button" class="btn btn-default btn-sm cpr-add-project">+ ${__("Add project")}</button>
			</div>
			<div class="cpr-kpi-grid"></div>
			<div class="cpr-legend"></div>
			<div class="cpr-chart-panel">
				<div class="cpr-chart-title"></div>
				<div class="cpr-chart-sub">${__(
					"Stacked bars show project mix · dashed line = monthly capacity ceiling"
				)}</div>
				<div class="cpr-chart-wrap">
					<div class="cpr-chart-canvas"></div>
					<div class="cpr-chart-tooltip"></div>
				</div>
			</div>
			<div class="cpr-table-heading cpr-table-heading-label">${__("Detailed monthly breakdown")}</div>
		</div>
	`);

	$main.find(".page-form").after(dashboard);

	dashboard.find(".cpr-view-toggle").on("click", ".cpr-toggle-btn", function () {
		const view = $(this).data("view");
		if (!view || view === cpr_view_mode) {
			return;
		}
		cpr_apply_view_mode(view);
	});

	dashboard.find(".cpr-horizon-toggle").on("click", ".cpr-toggle-btn", function () {
		const months = cint($(this).data("months"));
		if (!months) {
			return;
		}
		cpr_apply_horizon(months);
	});

	dashboard.find(".cpr-add-project").on("click", () => {
		frappe.new_doc("Project");
	});
}

function cpr_get_company(report) {
	const query_report = report || frappe.query_report;
	const company_filter = query_report.get_filter("company", false);
	return (
		query_report.get_filter_value("company") ||
		company_filter?.$input?.val() ||
		company_filter?.value ||
		frappe.defaults.get_user_default("Company")
	);
}

function cpr_get_default_bom_for_company(company) {
	if (!company) return "";
	const map = frappe.boot?.capacity_pipeline_default_boms || {};
	return map[company] || frappe.boot?.capacity_pipeline_default_bom || "";
}

function cpr_prepare_filters_before_refresh(report) {
	const query_report = report || frappe.query_report;
	return cpr_sync_default_bom_filter(query_report, { force: true }).then(async () => {
		cpr_detect_horizon_from_filters(query_report);
		await cpr_apply_horizon(cpr_horizon_months, false);
	});
}

function cpr_fetch_default_bom(company) {
	if (!company) {
		return Promise.resolve("");
	}
	return frappe
		.xcall(
			"fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report.get_default_bom",
			{ company }
		)
		.then((bom) => bom || "");
}

function cpr_sync_default_bom_filter(report, { force = false } = {}) {
	const query_report = report || frappe.query_report;
	if (!force && query_report.get_filter_value("bom")) {
		return Promise.resolve();
	}

	const company = cpr_get_company(query_report);
	if (!company) {
		return Promise.resolve();
	}

	return cpr_fetch_default_bom(company).then((bom) =>
		cpr_set_bom_filter_value(query_report, bom)
	);
}

function cpr_sync_bom_filter_from_boot(report, allow_fetch) {
	return cpr_sync_default_bom_filter(report, { force: allow_fetch });
}

async function cpr_set_bom_filter_value(report, bom) {
	const filter = report.get_filter("bom", false);
	if (!filter || !bom) return;

	report._no_refresh = true;
	filter.set_input(bom);
	await filter.set_value(bom);
	report._no_refresh = false;
}

function cpr_set_default_bom(refresh) {
	const report = frappe.query_report;
	return cpr_sync_default_bom_filter(report, { force: true }).then(() => {
		if (refresh) {
			report.refresh();
		}
	});
}

function cpr_update_header_bom() {
	const bom = frappe.query_report.get_filter_value("bom");
	const $bom = $(".cpr-header-bom");

	if (!bom) {
		$bom.hide().empty();
		return;
	}

	frappe.db.get_value("BOM", bom, ["item", "name"]).then((r) => {
		const item = r?.message?.item || bom;
		const name = r?.message?.name || bom;
		$bom
			.html(
				`${__("Capacity based on BOM")}: <a href="/app/bom/${encodeURIComponent(
					name
				)}" style="color:var(--primary,#2490ef)">${frappe.utils.escape_html(item)}</a>`
			)
			.show();
	});
}

function cpr_hide_default_chrome(report) {
	report.page.wrapper.find(".page-head").hide();
}

function cpr_months_between(from_date, to_date) {
	if (!from_date || !to_date) return 0;
	const from = frappe.datetime.str_to_obj(from_date);
	const to = frappe.datetime.str_to_obj(to_date);
	return (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth());
}

function cpr_count_months_in_range(from_date, to_date) {
	return cpr_months_between(from_date, to_date) + 1;
}

function cpr_calc_to_date(from_date, months) {
	return moment(from_date)
		.startOf("month")
		.add(months - 1, "months")
		.endOf("month")
		.format("YYYY-MM-DD");
}

function cpr_detect_horizon_from_filters(report) {
	const query_report = report || frappe.query_report;
	const from_date = query_report.get_filter_value("from_date");
	const to_date = query_report.get_filter_value("to_date");
	const count = cpr_count_months_in_range(from_date, to_date);
	const presets = [3, 6, 12, 18];

	if (presets.includes(count)) {
		cpr_horizon_months = count;
	}
}

function cpr_update_horizon_toggle_ui() {
	const from_date = frappe.query_report?.get_filter_value("from_date");
	const to_date = frappe.query_report?.get_filter_value("to_date");
	const count = cpr_count_months_in_range(from_date, to_date);
	const presets = [3, 6, 12, 18];

	$(".cpr-horizon-toggle .cpr-toggle-btn").each(function () {
		const months = cint($(this).data("months"));
		$(this).toggleClass("is-active", months === count && presets.includes(count));
	});

	if (presets.includes(count)) {
		cpr_horizon_months = count;
	}
}

async function cpr_apply_horizon(months, should_refresh = true) {
	const report = frappe.query_report;
	if (!report) {
		return;
	}

	cpr_horizon_months = months;
	cpr_update_horizon_toggle_ui();

	const from_date = report.get_filter_value("from_date");
	if (!from_date) {
		return;
	}

	const to_date = cpr_calc_to_date(from_date, months);
	const filter = report.get_filter("to_date", false);
	if (!filter) {
		return;
	}

	report._no_refresh = true;
	if (typeof filter.set_input === "function") {
		filter.set_input(to_date);
	}
	await filter.set_value(to_date);
	report._no_refresh = false;

	if (should_refresh) {
		report.refresh();
	}
}

function cpr_sync_to_date_filter(report) {
	cpr_apply_horizon(cpr_horizon_months, false);
}

function cpr_get_saved_column_widths() {
	try {
		return JSON.parse(localStorage.getItem("capacity_pipeline_report_column_widths")) || {};
	} catch (e) {
		return {};
	}
}

function cpr_save_column_widths(dt) {
	if (!dt?.datamanager?.getColumns) return;

	const widths = {};
	dt.datamanager.getColumns().forEach((col) => {
		const key = col.id || col.fieldname;
		if (!key || key.startsWith("_") || !col.width) return;
		widths[key] = Math.round(col.width);
	});

	localStorage.setItem("capacity_pipeline_report_column_widths", JSON.stringify(widths));
}

function cpr_bind_column_resize() {
	const dt = frappe.query_report.datatable;
	if (!dt?.wrapper) return;

	let was_resizing = false;

	$(dt.wrapper)
		.off("mousedown.cpr-col-resize dblclick.cpr-col-resize")
		.on("mousedown.cpr-col-resize", ".dt-cell__resize-handle", () => {
			was_resizing = true;
		})
		.on("dblclick.cpr-col-resize", ".dt-cell__resize-handle", () => {
			setTimeout(() => {
				cpr_save_column_widths(dt);
				cpr_fix_horizontal_scroll();
			}, 50);
		});

	$(document)
		.off("mouseup.cpr-col-resize")
		.on("mouseup.cpr-col-resize", () => {
			if (!was_resizing) return;
			was_resizing = false;
			setTimeout(() => {
				cpr_save_column_widths(dt);
				cpr_fix_horizontal_scroll();
			}, 0);
		});
}

function cpr_get_table_min_width(dt) {
	const cols = dt?.datamanager?.getColumns?.() || frappe.query_report.columns || [];
	return cols.reduce((sum, col) => sum + (parseInt(col.width, 10) || 96), 0);
}

function cpr_fix_horizontal_scroll() {
	const dt = frappe.query_report.datatable;
	if (!dt || !dt.wrapper) return;

	const min_width = cpr_get_table_min_width(dt);

	const $wrapper = $(dt.wrapper);
	$wrapper.css({ overflow: "visible", width: "100%" });
	$wrapper.find(".dt-scrollable").css({
		overflowX: "auto",
		overflowY: "visible",
		width: "100%",
	});
	$wrapper.find(".dt-scrollable .dt-header, .dt-scrollable .dt-body").css({
		minWidth: `${min_width}px`,
	});
}

function cpr_table_data_only_sites(rows) {
	/** Detailed breakdown table: Site project rows + summary rows only. */
	return (rows || []).filter((row) => {
		if (row.row_type !== "project") {
			return true;
		}
		return row.project_type === "Site";
	});
}

function cpr_sync_full_report_data(report) {
	if (report?.raw_data?.result) {
		report.cpr_all_data = report.prepare_data(report.raw_data.result);
		return;
	}
	if (report?.data?.length) {
		const has_non_site_project = report.data.some(
			(row) => row.row_type === "project" && row.project_type !== "Site"
		);
		if (has_non_site_project || !report.cpr_all_data) {
			report.cpr_all_data = report.data;
		}
	}
}

function cpr_apply_table_site_only_rows(report) {
	const query_report = report || frappe.query_report;
	if (!query_report) {
		return;
	}

	cpr_sync_full_report_data(query_report);
	const full_data = query_report.cpr_all_data || query_report.data || [];
	const table_data = cpr_table_data_only_sites(full_data);
	const already_site_only =
		(query_report.data || []).length === table_data.length &&
		(query_report.data || []).every(
			(row) => row.row_type !== "project" || row.project_type === "Site"
		);

	if (already_site_only) {
		return;
	}

	query_report.data = table_data;
	if (typeof query_report.render_datatable === "function") {
		query_report.render_datatable();
	}
}

function cpr_style_rows() {
	const data = frappe.query_report.data || [];
	const $rows = $(frappe.query_report.datatable?.wrapper).find(".dt-row");

	$rows.each(function (idx) {
		const row = data[idx];
		if (!row) return;

		const $row = $(this);
		$row.removeClass("cpr-summary-row cpr-separator-row cpr-project-row");

		const rt = cpr_get_row_type(row, row.project);
		if (rt === "separator") {
			$row.addClass("cpr-separator-row");
		} else if (["capacity", "demand", "free", "downtime"].includes(rt)) {
			$row.addClass("cpr-summary-row");
		} else if (rt === "project") {
			$row.addClass("cpr-project-row");
		}
	});
}

function cpr_fmt_label(rt, value, data) {
	const v = frappe.utils.escape_html(value || "");
	const sub = frappe.utils.escape_html(data.subtitle || "");

	if (rt === "project") {
		const name_html = data.project_id
			? `<a class="cpr-project-link" href="/app/project/${encodeURIComponent(
					data.project_id
			  )}">${v}</a>`
			: v;

		return `
		<div style="padding:6px 4px 4px;min-width:180px">
			<div style="font-weight:700;font-size:14px;color:#1f272e;line-height:1.35">${name_html}</div>
			${
				sub
					? `<div style="font-size:11px;color:#8d99a6;margin-top:3px;line-height:1.25">${sub}</div>`
					: ""
			}
		</div>`;
	}

	if (rt === "capacity") {
		return `<div style="padding:8px 4px;font-size:12px;color:#8d99a6">${v}</div>`;
	}

	if (rt === "downtime") {
		return `<div style="padding:8px 4px;font-size:12px;color:#8d99a6">${v}</div>`;
	}

	if (rt === "demand") {
		return `<div style="padding:8px 4px;font-size:13px;font-weight:700;color:#333">${v}</div>`;
	}

	if (rt === "free") {
		return `<div style="padding:8px 4px;font-size:12px;color:#8d99a6">${v}</div>`;
	}

	if (rt === "separator") {
		return `<div class="cpr-sep-cell"></div>`;
	}

	return v;
}

function cpr_fmt_project_cell(num, row_data, month_key) {
	const kitchen = cint(row_data[`${month_key}_kitchen`]);
	const wardrobe = cint(row_data[`${month_key}_wardrobe`]);
	const tooltip = `${__("Kitchen")}: ${kitchen} · ${__("Wardrobe")}: ${wardrobe}`;

	if (!num) {
		return `<div class="cpr-demand-badge" title="${frappe.utils.escape_html(
			tooltip
		)}" style="text-align:center;color:#d1d8dd;font-size:13px;padding:8px 0">—</div>`;
	}
	const c = CPR_PALETTE[(row_data.color_index || 0) % CPR_PALETTE.length];
	return `
	<div class="cpr-demand-badge" title="${frappe.utils.escape_html(tooltip)}" style="text-align:center;padding:6px 2px">
		<span style="
			display:inline-block;
			background:${c.bg};
			color:${c.text};
			border-radius:8px;
			padding:5px 12px;
			font-weight:700;
			font-size:14px;
			min-width:36px;
			line-height:1.3;
			box-shadow:0 1px 2px rgba(0,0,0,0.04)
		">${num}</span>
	</div>`;
}

function cpr_fmt_downtime_cell(num) {
	return `<div style="text-align:center;font-size:13px;font-weight:600;color:#7f8c8d;padding:8px 0">${num} ${__("mins")}</div>`;
}

function cpr_fmt_capacity_cell(value, fn, data) {
	const actual = data[fn + "_actual"];
	const theoretical = data[fn + "_theoretical"];
	let display;

	if (actual !== undefined && theoretical !== undefined) {
		display = `${actual}<span style="color:#bdc3c7;font-weight:500">/</span>${theoretical}`;
	} else {
		display = frappe.utils.escape_html(String(value || "0/0"));
	}

	return `<div style="text-align:center;font-size:14px;font-weight:600;color:#5a6773;padding:8px 0;line-height:1.35">${display}</div>`;
}

function cpr_get_capacity_actual(fn, row_data) {
	if (row_data?.[fn + "_actual"] !== undefined) {
		return cint(row_data[fn + "_actual"]);
	}

	const cap_row = (frappe.query_report?.cpr_all_data || frappe.query_report?.data || []).find(
		(r) => r.row_type === "capacity"
	);
	if (!cap_row) {
		return 0;
	}

	if (cap_row[fn + "_actual"] !== undefined) {
		return cint(cap_row[fn + "_actual"]);
	}

	const parts = String(cap_row[fn] || "").split("/");
	return cint(parts[0]);
}

function cpr_fmt_demand_cell(num, fn, data) {
	let pct = parseFloat(data[fn + "_pct"]);
	if (Number.isNaN(pct)) {
		const actual = cpr_get_capacity_actual(fn, data);
		pct = actual ? (num / actual) * 100 : 0;
	}

	let bg, textCol, pctCol;
	if (pct > 100) {
		bg = "#fde8ea";
		textCol = "#c0392b";
		pctCol = "#e74c3c";
	} else if (pct >= 80) {
		bg = "#fef9e7";
		textCol = "#b7770d";
		pctCol = "#d4ac0d";
	} else {
		bg = "#eafaf1";
		textCol = "#1e8449";
		pctCol = "#27ae60";
	}

	return `
	<div style="text-align:center;padding:4px 2px">
		<div style="
			display:inline-block;
			background:${bg};
			border-radius:8px;
			padding:5px 10px;
			min-width:48px;
			line-height:1.3;
			box-shadow:0 1px 2px rgba(0,0,0,0.04)
		">
			<div style="font-weight:800;font-size:15px;color:${textCol}">${num}</div>
			<div style="font-size:11px;font-weight:600;color:${pctCol}">${pct.toFixed(0)}%</div>
		</div>
	</div>`;
}

function cpr_fmt_free_cell(num) {
	if (num < 0) {
		return `<div style="text-align:center;font-weight:700;font-size:14px;color:#c0392b;padding:8px 0">${num}</div>`;
	}
	return `<div style="text-align:center;font-size:14px;font-weight:600;color:#5a6773;padding:8px 0">${num}</div>`;
}

// ---------------------------------------------------------------------------
// Dashboard (UI only — aggregates existing report rows, no new backend logic)
// ---------------------------------------------------------------------------

function cpr_get_period_columns() {
	return (frappe.query_report.columns || [])
		.filter(
			(col) =>
				col.fieldname &&
				(col.fieldname.startsWith("m_") || col.fieldname.startsWith("w_"))
		)
		.map((col) => ({ key: col.fieldname, label: col.label }));
}

function cpr_is_weekly_granularity() {
	return frappe.query_report?.get_filter_value("granularity") === "Weekly";
}

function cpr_update_view_toggle_ui() {
	$(".cpr-view-toggle .cpr-toggle-btn").each(function () {
		const view = $(this).data("view");
		$(this).toggleClass("is-active", view === cpr_view_mode);
	});
}

function cpr_sync_view_mode_from_filters() {
	if (cpr_view_mode === "quarterly") {
		cpr_update_view_toggle_ui();
		return;
	}
	const granularity = frappe.query_report?.get_filter_value("granularity");
	cpr_view_mode = granularity === "Weekly" ? "weekly" : "monthly";
	cpr_update_view_toggle_ui();
}

async function cpr_set_granularity_filter(granularity) {
	const report = frappe.query_report;
	const filter = report.get_filter("granularity", false);
	if (!filter) {
		return;
	}

	report._no_refresh = true;
	await filter.set_value(granularity);
	report._no_refresh = false;
}

async function cpr_apply_view_mode(view) {
	cpr_view_mode = view;
	cpr_update_view_toggle_ui();

	if (view === "quarterly") {
		cpr_render_dashboard();
		return;
	}

	const granularity = view === "weekly" ? "Weekly" : "Monthly";
	await cpr_set_granularity_filter(granularity);
	frappe.query_report.refresh();
}

function cpr_palette_slot(color_index) {
	return CPR_PALETTE[(color_index || 0) % CPR_PALETTE.length];
}

function cpr_chart_label(row) {
	return row.chart_label || row.project || "";
}

function cpr_rollup_rows_by_chart_label(rows) {
	const merged = {};
	const period_keys = cpr_get_period_columns().map((col) => col.key);

	(rows || []).forEach((row) => {
		const label = cpr_chart_label(row);
		if (!label) {
			return;
		}

		if (!merged[label]) {
			merged[label] = {
				...row,
				project: label,
				chart_label: label,
			};
			return;
		}

		const target = merged[label];
		period_keys.forEach((key) => {
			target[key] = cint(target[key]) + cint(row[key]);
			target[`${key}_kitchen`] = cint(target[`${key}_kitchen`]) + cint(row[`${key}_kitchen`]);
			target[`${key}_wardrobe`] =
				cint(target[`${key}_wardrobe`]) + cint(row[`${key}_wardrobe`]);
		});
	});

	return Object.values(merged);
}

function cpr_get_chart_project_rows(rows) {
	/** Roll child unit demand up to Site names for chart legend and stacked bars. */
	const project_rows = (rows || []).filter((r) => r.row_type === "project");
	const detail_rows = project_rows.filter((r) => r.project_type !== "Site");
	const source = detail_rows.length
		? detail_rows
		: project_rows.filter((r) => r.project_type === "Site");
	return cpr_rollup_rows_by_chart_label(source);
}

function cpr_collect_dashboard_data() {
	const rows =
		frappe.query_report.cpr_all_data || frappe.query_report.data || [];
	const period_cols = cpr_get_period_columns();
	const is_weekly = cpr_is_weekly_granularity();
	const chart_project_rows = cpr_get_chart_project_rows(rows);
	const capacity_row = rows.find((r) => r.row_type === "capacity") || {};
	const demand_row = rows.find((r) => r.row_type === "demand") || {};
	const free_row = rows.find((r) => r.row_type === "free") || {};

	const months = period_cols.map(({ key, label }) => {
		const capacity = cpr_get_capacity_actual(key, capacity_row);
		const demand = cint(demand_row[key]);
		const free = cint(free_row[key]);
		const projects = chart_project_rows
			.map((p) => ({
				name: cpr_chart_label(p),
				id: p.project_id,
				subtitle: p.subtitle || "",
				color_index: p.color_index || 0,
				value: cint(p[key]),
				kitchen: cint(p[`${key}_kitchen`]),
				wardrobe: cint(p[`${key}_wardrobe`]),
			}))
			.filter((p) => p.value > 0);

		return {
			key,
			label,
			capacity,
			demand,
			free,
			projects,
			over: capacity > 0 && demand > capacity,
		};
	});

	const util_pcts = months.filter((m) => m.capacity > 0).map((m) => (m.demand / m.capacity) * 100);
	const avg_util = util_pcts.length
		? util_pcts.reduce((sum, pct) => sum + pct, 0) / util_pcts.length
		: 0;
	const over_months = months.filter((m) => m.over);
	const total_demand = months.reduce((sum, m) => sum + m.demand, 0);
	const total_free = months.reduce((sum, m) => sum + Math.max(0, m.free), 0);
	const capacities = months.map((m) => m.capacity).filter((c) => c > 0);
	const avg_capacity = capacities.length
		? Math.round(capacities.reduce((sum, c) => sum + c, 0) / capacities.length)
		: 0;

	const from_date = frappe.query_report.get_filter_value("from_date");
	const to_date = frappe.query_report.get_filter_value("to_date");

	return {
		project_rows: chart_project_rows,
		months,
		is_weekly,
		total_demand,
		avg_util,
		over_months,
		total_free,
		avg_capacity,
		project_count: chart_project_rows.length,
		from_date,
		to_date,
	};
}

function cpr_aggregate_quarterly(months) {
	const quarters = [];

	for (let i = 0; i < months.length; i += 3) {
		const chunk = months.slice(i, i + 3);
		if (!chunk.length) {
			continue;
		}

		const project_map = {};
		chunk.forEach((month) => {
			month.projects.forEach((proj) => {
				if (!project_map[proj.name]) {
					project_map[proj.name] = { ...proj, value: 0, kitchen: 0, wardrobe: 0 };
				}
				project_map[proj.name].value += proj.value;
				project_map[proj.name].kitchen += proj.kitchen;
				project_map[proj.name].wardrobe += proj.wardrobe;
			});
		});

		const capacity = chunk.reduce((sum, m) => sum + m.capacity, 0);
		const demand = chunk.reduce((sum, m) => sum + m.demand, 0);
		const range_label = `${chunk[0].label} – ${chunk[chunk.length - 1].label}`;

		quarters.push({
			key: chunk.map((m) => m.key).join("_"),
			label: range_label,
			full_label: range_label,
			capacity,
			demand,
			free: capacity - demand,
			projects: Object.values(project_map).filter((p) => p.value > 0),
			over: chunk.some((m) => m.over),
		});
	}

	return quarters;
}

function cpr_get_chart_dimensions(period_count, data) {
	const is_quarterly = cpr_view_mode === "quarterly";
	const is_weekly = data.is_weekly && !is_quarterly;

	let slot_min = 72;
	if (is_quarterly) {
		slot_min = 96;
	} else if (is_weekly) {
		slot_min = period_count > 20 ? 40 : 48;
	}

	const width = Math.max(640, period_count * slot_min + 80);
	const two_line_labels = true;
	const bottom_pad = is_quarterly ? 50 : period_count > 12 ? 48 : 44;
	const chart_height = 310;

	return { width, slot_min, two_line_labels, bottom_pad, chart_height };
}

function cpr_split_period_label(label) {
	const text = (label || "").trim();
	if (!text) {
		return { line1: "", line2: "" };
	}

	// Quarterly range, e.g. JUN '26 – AUG '26
	if (text.includes("–")) {
		const parts = text.split("–").map((p) => p.trim());
		const start = parts[0] || "";
		const end = parts[parts.length - 1] || "";
		const start_bits = start.split(/\s+/);
		const end_bits = end.split(/\s+/);
		const year = end_bits.slice(1).join(" ") || start_bits.slice(1).join(" ");
		if (start_bits[0] === end_bits[0]) {
			return { line1: start_bits[0], line2: year };
		}
		return {
			line1: `${start_bits[0]} – ${end_bits[0]}`,
			line2: year,
		};
	}

	const bits = text.split(/\s+/);
	if (bits.length >= 2) {
		// Weekly: 02 JUN
		if (/^\d+$/.test(bits[0])) {
			return { line1: bits[0], line2: bits.slice(1).join(" ") };
		}
		// Monthly: JUN '26
		return { line1: bits[0], line2: bits.slice(1).join(" ") };
	}

	return { line1: text, line2: "" };
}

function cpr_render_x_axis_label(cx, base_y, label) {
	const { line1, line2 } = cpr_split_period_label(label);
	const safe1 = frappe.utils.escape_html(line1);
	const safe2 = frappe.utils.escape_html(line2);

	if (line2) {
		return `
			<text class="cpr-chart-x-label" x="${cx}" y="${base_y - 11}" text-anchor="middle">${safe1}</text>
			<text class="cpr-chart-x-label cpr-chart-x-label--sub" x="${cx}" y="${base_y + 1}" text-anchor="middle">${safe2}</text>`;
	}

	return `<text class="cpr-chart-x-label" x="${cx}" y="${base_y}" text-anchor="middle">${safe1}</text>`;
}

function cpr_format_month_list(months) {
	if (!months.length) {
		return "";
	}
	if (months.length === 1) {
		return months[0].label;
	}
	return `${months[0].label} & ${months[months.length - 1].label}`;
}

function cpr_util_status(avg_util) {
	if (avg_util > 100) {
		return __("overloaded over horizon");
	}
	if (avg_util >= 80) {
		return __("healthy load over horizon");
	}
	return __("capacity headroom available");
}

let cpr_dashboard_render_seq = 0;

function cpr_render_dashboard(report) {
	if (!cpr_is_capacity_pipeline_report(report)) {
		return;
	}
	const query_report = report || frappe.query_report;
	const $dash = $(".cpr-dashboard");
	if (!$dash.length || !query_report?.data) {
		return;
	}

	const render_seq = ++cpr_dashboard_render_seq;
	cpr_update_horizon_toggle_ui();

	const data = cpr_collect_dashboard_data();
	const chart_periods =
		cpr_view_mode === "quarterly" ? cpr_aggregate_quarterly(data.months) : data.months;

	cpr_render_controls_meta($dash, data);
	cpr_render_kpi_cards($dash, data);
	cpr_render_legend($dash, data);
	cpr_render_chart($dash, data, chart_periods);

	const period_label = data.is_weekly
		? __("Detailed weekly breakdown")
		: __("Detailed monthly breakdown");
	$dash.find(".cpr-table-heading-label").text(period_label);
	let chart_sub = __("Stacked bars show project mix · dashed line = monthly capacity ceiling");
	if (cpr_view_mode === "quarterly") {
		chart_sub = __("Stacked bars by quarter (3 months) · dashed line = capacity");
	} else if (data.is_weekly) {
		chart_sub = __("Stacked bars show project mix · dashed line = weekly capacity ceiling");
	}
	$dash.find(".cpr-chart-sub").text(chart_sub);

	cpr_load_pipeline_totals(query_report).then((totals) => {
		if (render_seq !== cpr_dashboard_render_seq || !totals || !frappe.query_report?.data) {
			return;
		}
		data.pipeline_totals = totals;
		cpr_render_controls_meta($dash, data);
		cpr_render_kpi_cards($dash, data);
	});
}

function cpr_pipeline_totals_filter_key(query_report) {
	const filters = query_report?.get_filter_values?.() || {};
	return [filters.company, filters.from_date, filters.to_date, filters.project].join(
		"|"
	);
}

function cpr_sync_pipeline_totals_cache(query_report) {
	const sig = cpr_pipeline_totals_filter_key(query_report);
	if (sig !== cpr_pipeline_totals_filter_sig) {
		cpr_pipeline_totals_filter_sig = sig;
		cpr_last_pipeline_totals = null;
	}
}

function cpr_load_pipeline_totals(query_report) {
	const filters = query_report?.get_filter_values
		? query_report.get_filter_values()
		: {};

	return frappe
		.xcall(
			"fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report.get_pipeline_totals",
			{ filters }
		)
		.then((totals) => {
			cpr_last_pipeline_totals = totals;
			return totals;
		})
		.catch(() => cpr_last_pipeline_totals || { total_demand: 0, project_count: 0 });
}

function cpr_render_controls_meta($dash, data) {
	const baseline = data.avg_capacity || 0;
	const unit = data.is_weekly ? __("kitchens / week") : __("kitchens / month");
	const pipeline_count =
		data.pipeline_totals?.project_count ?? data.project_count;
	const bom_count = data.project_count;
	const bom_note =
		bom_count !== pipeline_count
			? ` (${bom_count} ${__("for selected BOM")})`
			: "";

	const text = `${__("Capacity baseline")}: ${baseline} ${unit} · ${pipeline_count} ${__(
		"projects in pipeline"
	)}${bom_note}`;
	$dash.find(".cpr-controls-meta").text(text);
}

function cpr_render_kpi_cards($dash, data) {
	const over_labels = cpr_format_month_list(data.over_months);
	const over_period = data.is_weekly ? __("weeks") : __("months");
	const over_foot = data.over_months.length
		? `${over_labels} · ${__("need to re-sequence")}`
		: `${__("all")} ${over_period} ${__("within capacity")}`;

	const pipeline_totals = data.pipeline_totals || cpr_last_pipeline_totals;
	const pipeline_total =
		pipeline_totals?.total_kitchens ?? pipeline_totals?.total_demand;
	const pipeline_value =
		pipeline_total === undefined || pipeline_total === null ? "—" : pipeline_total;

	const cards = [
		{
			cls: "cpr-kpi-card--grey",
			label: __("Total kitchens in pipeline"),
			value: pipeline_value,
			value_cls: "",
			foot: __("kitchen units in pipeline"),
		},
		{
			cls: "cpr-kpi-card--green",
			label: __("Avg capacity utilisation"),
			value: `${Math.round(data.avg_util)}%`,
			value_cls: "cpr-kpi-value--green",
			foot: cpr_util_status(data.avg_util),
		},
		{
			cls: "cpr-kpi-card--red",
			label: data.is_weekly ? __("Weeks over capacity") : __("Months over capacity"),
			value: data.over_months.length,
			value_cls: "cpr-kpi-value--red",
			foot: over_foot,
		},
		{
			cls: "cpr-kpi-card--orange",
			label: __("Capacity available"),
			value: data.total_free,
			value_cls: "cpr-kpi-value--orange",
			foot: `${__("slots free for new work · next")} ${cpr_horizon_months}${__("mo")}`,
		},
	];

	const html = cards
		.map(
			(card) => `
		<div class="cpr-kpi-card ${card.cls}">
			<div class="cpr-kpi-label">${card.label}</div>
			<div class="cpr-kpi-value ${card.value_cls}">${card.value}</div>
			<div class="cpr-kpi-foot">${card.foot}</div>
		</div>`
		)
		.join("");

	$dash.find(".cpr-kpi-grid").html(html);
}

function cpr_render_legend($dash, data) {
	const items = data.project_rows
		.map((proj) => {
			const palette = cpr_palette_slot(proj.color_index);
			return `
			<span class="cpr-legend-item">
				<span class="cpr-legend-swatch" style="background:${palette.chart}"></span>
				<span style="color:${palette.text}">${frappe.utils.escape_html(cpr_chart_label(proj))}</span>
			</span>`;
		})
		.join("");

	const cap = data.avg_capacity || 0;
	const cap_unit = data.is_weekly ? __("wk") : __("mo");

	$dash.find(".cpr-legend").html(`
		${items}
		<span class="cpr-legend-capacity">— — — ${__("Production capacity")} (${cap}/${cap_unit})</span>
	`);
}

function cpr_render_chart($dash, data, periods) {
	const from_label = data.from_date
		? frappe.datetime.str_to_user(data.from_date)
		: "";
	const to_label = data.to_date ? frappe.datetime.str_to_user(data.to_date) : "";
	let view_label;
	if (cpr_view_mode === "quarterly") {
		view_label = __("Quarterly kitchen demand vs capacity");
	} else if (data.is_weekly) {
		view_label = __("Weekly kitchen demand vs capacity");
	} else {
		view_label = __("Monthly kitchen demand vs capacity");
	}

	$dash.find(".cpr-chart-title").text(`${view_label} · ${from_label} — ${to_label}`);

	if (!periods.length) {
		$dash.find(".cpr-chart-canvas").html(
			`<div style="padding:40px;text-align:center;color:#8d99a6">${__("No data for selected horizon")}</div>`
		);
		return;
	}

	const dims = cpr_get_chart_dimensions(periods.length, data);
	const width = dims.width;
	const height = dims.chart_height;
	const pad = { top: 28, right: 72, bottom: dims.bottom_pad, left: 36 };
	const chart_w = width - pad.left - pad.right;
	const chart_h = height - pad.top - pad.bottom;

	const max_demand = Math.max(...periods.map((p) => p.demand), 0);
	const max_capacity = Math.max(...periods.map((p) => p.capacity), 0);
	const y_max = Math.max(max_demand, max_capacity, 1);
	const y_scale = (val) => pad.top + chart_h - (val / y_max) * chart_h;
	const slot_w = Math.max(chart_w / periods.length, 1);
	const bar_w = Math.max(8, Math.min(42, slot_w - 12));

	let bars_svg = "";
	let cap_points = "";

	periods.forEach((period, idx) => {
		const cx = pad.left + slot_w * idx + slot_w / 2;
		let y_cursor = pad.top + chart_h;
		const stack_projects = [...(period.projects || [])].sort(
			(a, b) => (a.color_index || 0) - (b.color_index || 0)
		);
		const stack_total = stack_projects.reduce((sum, p) => sum + p.value, 0);
		const bar_total = period.demand > 0 ? period.demand : stack_total;

		stack_projects.forEach((proj) => {
			if (!proj.value) {
				return;
			}
			const share = stack_total > 0 ? proj.value / stack_total : 0;
			const seg_val = bar_total * share;
			const seg_h = (seg_val / y_max) * chart_h;
			if (seg_h <= 0) {
				return;
			}
			const y = y_cursor - seg_h;
			const palette = cpr_palette_slot(proj.color_index);
			const tooltip = `${frappe.utils.escape_html(proj.name)}: ${proj.value}\\n${__(
				"Kitchen"
			)}: ${proj.kitchen} · ${__("Wardrobe")}: ${proj.wardrobe}`;
			bars_svg += `
				<rect x="${cx - bar_w / 2}" y="${y}" width="${bar_w}" height="${seg_h}" fill="${palette.chart}" rx="2">
					<title>${tooltip}</title>
				</rect>`;
			if (seg_h >= 12 && proj.value > 0) {
				bars_svg += `<text class="cpr-chart-seg-label" x="${cx}" y="${y + seg_h / 2 + 4}">${proj.value}</text>`;
			}
			y_cursor = y;
		});

		if (period.demand > 0) {
			bars_svg += `<text class="cpr-chart-total-label" x="${cx}" y="${y_scale(period.demand) - 6}">${period.demand}</text>`;
		}

		bars_svg += cpr_render_x_axis_label(cx, height - 8, period.label);

		const cap_y = y_scale(period.capacity);
		cap_points += `${cx},${cap_y} `;
	});

	let grid_svg = "";
	const y_ticks = 5;
	for (let i = 0; i <= y_ticks; i += 1) {
		const val = Math.round((y_max / y_ticks) * i);
		const y = y_scale(val);
		grid_svg += `<line class="cpr-chart-axis" x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" />`;
		grid_svg += `<text class="cpr-chart-y-label" x="${pad.left - 6}" y="${y + 4}">${val}</text>`;
	}

	const cap_label_x = width - pad.right + 4;
	const avg_cap_y = y_scale(data.avg_capacity || 0);
	const cap_unit = data.is_weekly ? __("wk") : __("mo");

	const svg = `
		<svg class="cpr-chart-svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}"
			preserveAspectRatio="xMinYMin meet" role="img" aria-label="${__(
				"Demand vs capacity chart"
			)}">
			${grid_svg}
			${bars_svg}
			<polyline class="cpr-chart-cap-line" points="${cap_points.trim()}" />
			<text class="cpr-chart-cap-label" x="${cap_label_x}" y="${avg_cap_y + 4}">${__(
				"Capacity"
			)}: ${data.avg_capacity || 0}/${cap_unit}</text>
			<g class="cpr-chart-hover-layer"></g>
		</svg>`;

	const $canvas = $dash.find(".cpr-chart-canvas");
	let $tooltip = $dash.find(".cpr-chart-tooltip");
	if (!$tooltip.length) {
		$dash.find(".cpr-chart-wrap").append('<div class="cpr-chart-tooltip"></div>');
		$tooltip = $dash.find(".cpr-chart-tooltip");
	}
	$canvas.html(svg);

	cpr_bind_chart_hover($canvas, $tooltip, periods, { pad, slot_w, chart_h, height, y_scale });
}

function cpr_bind_chart_hover($canvas, $tooltip, periods, layout) {
	const { pad, slot_w, chart_h, height, y_scale } = layout;

	$canvas.off("mousemove.cpr-chart mouseleave.cpr-chart");

	$canvas.on("mousemove.cpr-chart", "svg", function (e) {
		const svgEl = this;
		const rect = svgEl.getBoundingClientRect();
		const view_w = svgEl.viewBox.baseVal.width || rect.width;
		const x = ((e.clientX - rect.left) / rect.width) * view_w;
		const idx = Math.floor((x - pad.left) / slot_w);

		if (idx < 0 || idx >= periods.length) {
			cpr_hide_chart_hover($canvas, $tooltip);
			return;
		}

		const period = periods[idx];
		const cx = pad.left + slot_w * idx + slot_w / 2;
		const cap_y = y_scale(period.capacity);
		const util = period.capacity ? Math.round((period.demand / period.capacity) * 100) : 0;
		const free = period.capacity - period.demand;
		const over = period.capacity > 0 && period.demand > period.capacity;
		const free_cls = free < 0 ? "cpr-chart-tooltip-row--over" : "cpr-chart-tooltip-row--ok";

		let projects_html = "";
		if (period.projects?.length) {
			projects_html = `<div class="cpr-chart-tooltip-divider"></div>`;
			period.projects.forEach((proj) => {
				projects_html += `<div class="cpr-chart-tooltip-project">${frappe.utils.escape_html(
					proj.name
				)}: ${proj.value} · ${__("Kitchen")} ${proj.kitchen} · ${__("Wardrobe")} ${
					proj.wardrobe
				}</div>`;
			});
		}

		const period_title = period.full_label || period.label;
		$tooltip.html(`
			<div class="cpr-chart-tooltip-title">${frappe.utils.escape_html(period_title)}</div>
			<div class="cpr-chart-tooltip-row">
				<span>${__("Demand")}</span><strong>${period.demand}</strong>
			</div>
			<div class="cpr-chart-tooltip-row cpr-chart-tooltip-row--capacity">
				<span>${__("Capacity")}</span><strong>${period.capacity}</strong>
			</div>
			<div class="cpr-chart-tooltip-row">
				<span>${__("Utilisation")}</span><strong>${util}%</strong>
			</div>
			<div class="cpr-chart-tooltip-row ${free_cls}">
				<span>${__("Free capacity")}</span><strong>${free}</strong>
			</div>
			${
				over
					? `<div class="cpr-chart-tooltip-row cpr-chart-tooltip-row--over"><span>${__(
							"Status"
					  )}</span><strong>${__("Over capacity")}</strong></div>`
					: ""
			}
			${projects_html}
		`);

		const $wrap = $canvas.closest(".cpr-chart-wrap");
		const wrap_rect = $wrap[0].getBoundingClientRect();

		let left = e.clientX - wrap_rect.left + 14;
		let top = e.clientY - wrap_rect.top + 12;
		const tip_w = 220;
		const tip_h = $tooltip.outerHeight() || 140;

		if (left + tip_w > $wrap.innerWidth() - 8) {
			left = e.clientX - wrap_rect.left - tip_w - 14;
		}
		if (top + tip_h > $wrap.innerHeight() - 8) {
			top = $wrap.innerHeight() - tip_h - 8;
		}
		if (top < 8) {
			top = 8;
		}

		$tooltip.css({ left, top }).show();

		const hover_layer = svgEl.querySelector(".cpr-chart-hover-layer");
		if (hover_layer) {
			hover_layer.innerHTML = `
				<line class="cpr-chart-hover-line"
					x1="${cx}" y1="${pad.top}" x2="${cx}" y2="${pad.top + chart_h}" />
				<circle class="cpr-chart-hover-cap" cx="${cx}" cy="${cap_y}" r="4" />
			`;
		}
	});

	$canvas.on("mouseleave.cpr-chart", "svg", function () {
		cpr_hide_chart_hover($canvas, $tooltip);
	});

	$canvas.closest(".cpr-chart-wrap").off("mouseleave.cpr-chart").on("mouseleave.cpr-chart", function () {
		cpr_hide_chart_hover($canvas, $tooltip);
	});
}

function cpr_hide_chart_hover($canvas, $tooltip) {
	$tooltip.hide();
	$canvas.find(".cpr-chart-hover-layer").empty();
}
