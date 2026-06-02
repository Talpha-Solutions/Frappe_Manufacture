// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const CPR_PALETTE = [
	{ bg: "#d4e8f7", text: "#1a5276" },
	{ bg: "#e8d5f5", text: "#6c3483" },
	{ bg: "#d5f5e3", text: "#1e8449" },
	{ bg: "#fdebd0", text: "#7d6608" },
	{ bg: "#fadbd8", text: "#922b21" },
	{ bg: "#d1f2eb", text: "#117a65" },
	{ bg: "#e8daef", text: "#512e5f" },
	{ bg: "#fcf3cf", text: "#7d6608" },
];

frappe.query_reports["Capacity Pipeline Report"] = {
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
				cpr_sync_to_date_filter();
			},
		},
		{
			label: __("To Date"),
			fieldname: "to_date",
			fieldtype: "Date",
			default: frappe.datetime.month_end(
				frappe.datetime.add_months(frappe.datetime.month_start(), 11)
			),
			reqd: 1,
		},
		{
			label: __("BOM"),
			fieldname: "bom",
			fieldtype: "Link",
			options: "BOM",
			default: frappe.boot?.capacity_pipeline_default_bom || "",
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
	],

	onload(report) {
		cpr_inject_styles();
		cpr_setup_header(report);
		cpr_hide_default_chrome(report);
		return cpr_prepare_filters_before_refresh(report);
	},

	get_datatable_options(options) {
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
		cpr_style_rows();
		cpr_bind_column_resize();
		cpr_fix_horizontal_scroll();
		cpr_update_header_bom();
	},

	after_refresh(report) {
		cpr_sync_bom_filter_from_boot(report);
	},

	formatter(value, row, column, data, default_formatter) {
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

		if (rt === "project") return cpr_fmt_project_cell(num, row_data.color_index);
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
	if (label === __("Capacity / month") || label === "Capacity / month") {
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

function cpr_inject_styles() {
	if (document.getElementById("cpr-report-styles")) return;

	const css = `
		.cpr-page .page-head { display: none !important; }
		.cpr-page .layout-main-section { background: #f4f5f7; padding: 0 16px 24px; }
		.cpr-header { background: #fff; border: 1px solid #e8eaed; border-bottom: none; border-radius: 8px 8px 0 0; padding: 20px 24px 14px; margin-top: 12px; }
		.cpr-header-title { font-size: 18px; font-weight: 700; color: #1f272e; line-height: 1.3; margin: 0; }
		.cpr-header-sub { font-size: 12px; color: #8d99a6; margin-top: 6px; line-height: 1.4; }
		.cpr-page .page-form { background: #fff; border-left: 1px solid #e8eaed; border-right: 1px solid #e8eaed; border-bottom: none; border-top: none; margin-top: 0; padding: 8px 16px 4px; }
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
	`;

	$("<style>", { id: "cpr-report-styles", text: css }).appendTo("head");
}

function cpr_setup_header(report) {
	const $main = report.page.main;
	$main.closest(".layout-main-section").addClass("cpr-page");

	if (!$main.find(".cpr-header").length) {
		const header = $(`
			<div class="cpr-header">
				<h4 class="cpr-header-title">${__("Project allocation by month")}</h4>
				<div class="cpr-header-sub">${__(
					"Click a project to see its production load · numbers = kitchens produced that month (from Job Card actual time) · drag column edges to resize"
				)}</div>
				<div class="cpr-header-bom" style="display:none;font-size:11px;color:#5a6773;margin-top:4px"></div>
			</div>
		`);
		$main.find(".page-form").before(header);
	}
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
	return cpr_sync_bom_filter_from_boot(query_report, true).then(() => {
		const from_date = query_report.get_filter_value("from_date");
		const to_date = query_report.get_filter_value("to_date");
		if (from_date && (!to_date || cpr_months_between(from_date, to_date) < 11)) {
			cpr_sync_to_date_filter(query_report);
		}
	});
}

function cpr_sync_bom_filter_from_boot(report, allow_fetch) {
	const query_report = report || frappe.query_report;
	if (query_report.get_filter_value("bom")) {
		return Promise.resolve();
	}

	const company = cpr_get_company(query_report);
	const boot_bom = cpr_get_default_bom_for_company(company);
	if (boot_bom) {
		return cpr_set_bom_filter_value(query_report, boot_bom);
	}

	if (!allow_fetch || !company) {
		return Promise.resolve();
	}

	return frappe
		.xcall(
			"fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report.get_default_bom",
			{ company }
		)
		.then((bom) => cpr_set_bom_filter_value(query_report, bom));
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
	const company = cpr_get_company(report);
	const boot_bom = cpr_get_default_bom_for_company(company);

	const apply = boot_bom
		? cpr_set_bom_filter_value(report, boot_bom)
		: cpr_sync_bom_filter_from_boot(report, true);

	return apply.then(() => {
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

function cpr_sync_to_date_filter(report) {
	const query_report = report || frappe.query_report;
	const from_date = query_report.get_filter_value("from_date");
	if (!from_date) return;

	const to_date = frappe.datetime.month_end(frappe.datetime.add_months(from_date, 11));
	query_report.set_filter_value("to_date", to_date);
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
		const sub = frappe.utils.escape_html(data.subtitle || "");
		return `<div style="padding:8px 4px;font-size:12px;color:#8d99a6">
			<div>${v}</div>
			${sub ? `<div style="font-size:10px;color:#aeb6bf;margin-top:2px">${sub}</div>` : ""}
		</div>`;
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

function cpr_fmt_project_cell(num, idx) {
	if (!num) {
		return `<div style="text-align:center;color:#d1d8dd;font-size:13px;padding:8px 0">—</div>`;
	}
	const c = CPR_PALETTE[(idx || 0) % CPR_PALETTE.length];
	return `
	<div style="text-align:center;padding:6px 2px">
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

	const cap_row = (frappe.query_report?.data || []).find((r) => r.row_type === "capacity");
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
