// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Project Production Time Summary"] = {
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
		const extra_time_fields = ["extra_time", "task_extra_time"];
		if (!extra_time_fields.includes(column.fieldname)) {
			return default_formatter(value, row, column, data);
		}

		const amount = flt(data?.[column.fieldname] ?? value);
		if (!amount) {
			return default_formatter(value, row, column, data);
		}

		const is_negative = amount < 0;
		const color = is_negative ? "green" : "red";
		const precision = cint(column.precision) || 2;
		const formatted = format_number(Math.abs(amount), null, precision);
		const display_value = is_negative ? `(${formatted})` : formatted;

		return `<div style="color:${color}!important;font-weight:400;text-align:right;">${display_value}</div>`;
	},
};
