// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Manufacturing Cost Summary"] = {
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
				var fiscal_year = query_report.get_values().fiscal_year;
				if (!fiscal_year) {
					return;
				}
				frappe.model.with_doc("Fiscal Year", fiscal_year, function (r) {
					var fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
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
			label: __("Project"),
			fieldname: "project",
			fieldtype: "Link",
			options: "Project",
		},
		{
			label: __("Work Order Status"),
			fieldname: "status",
			fieldtype: "Select",
			options: ["", "Not Started", "In Process", "Completed", "Stopped", "Closed"],
		},
	],

	formatter(value, row, column, data, default_formatter) {
		const extra_cost_fields = ["extra_cost", "task_extra_cost"];
		if (!extra_cost_fields.includes(column.fieldname)) {
			return default_formatter(value, row, column, data);
		}

		const amount = flt(data?.[column.fieldname] ?? value);
		if (!amount) {
			return default_formatter(value, row, column, data);
		}

		const currency = column.options;
		const is_negative = amount < 0;
		const color = is_negative ? "green" : "red";
		const display_value = is_negative
			? mcs_format_negative_extra_cost(Math.abs(amount), currency)
			: format_currency(Math.abs(amount), currency);

		return `<div style="color:${color}!important;font-weight:400;text-align:right;">${display_value}</div>`;
	},
};

function mcs_format_negative_extra_cost(amount, currency) {
	const symbol = get_currency_symbol(currency);
	const number_part = format_number(
		amount,
		get_number_format(currency),
		frappe.boot.sysdefaults.currency_precision || 2
	);
	const show_symbol_on_right =
		frappe.model.get_value(":Currency", currency, "symbol_on_right") ?? false;

	if (!symbol) {
		return `(${number_part})`;
	}

	if (show_symbol_on_right) {
		return `(${number_part}) ${__(symbol)}`;
	}

	return `${__(symbol)} (${number_part})`;
}
