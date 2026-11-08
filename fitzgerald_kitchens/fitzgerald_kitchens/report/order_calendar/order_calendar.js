// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Order Calendar"] = {
	filters: [
		{
			fieldname: "pre_production_plan",
			label: __("Pre Production Plans"),
			fieldtype: "MultiSelectList",
			get_data: (txt) => frappe.db.get_link_options("Pre Production Plan", txt),
			description: __("Leave blank for every plan"),
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			description: __("Stock counted from this warehouse (and those under it); all of the company's if blank"),
		},
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: ["Weekly", "Monthly"],
			default: "Weekly",
		},
		{ fieldname: "periods", label: __("Periods"), fieldtype: "Int", default: 12 },
		{
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: ["Qty", "Value"],
			default: "Qty",
		},
		{
			fieldname: "default_delivery_date",
			label: __("Delivery Date (if not set)"),
			fieldtype: "Date",
			description: __("For units with no delivery date, e.g. a plan with no Units table yet"),
		},
		{
			fieldname: "manufacturing_days",
			label: __("Manufactured: Days Before Delivery"),
			fieldtype: "Int",
			default: 14,
		},
		{ fieldname: "bought_in_days", label: __("Bought-in: Days Before Delivery"), fieldtype: "Int", default: 0 },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const key = column.fieldname;
		const numeric = key === "overdue" || key === "later" || key === "total" || /^p\d+$/.test(key);
		if (numeric && data && !flt(data[key])) return `<span class="text-muted">-</span>`;
		if (key === "overdue" && data && flt(data.overdue)) return `<span class="text-danger"><b>${value}</b></span>`;
		return value;
	},
};
