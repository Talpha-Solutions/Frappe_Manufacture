// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const SMR_STATUS_COLOURS = {
	"Order Now": "red",
	Short: "orange",
	"Covered by Orders": "blue",
	"In Stock": "green",
	"Not a Stock Item": "gray",
};

frappe.query_reports["Site Material Requirements"] = {
	filters: [
		{
			fieldname: "site_project",
			label: __("Site Project"),
			fieldtype: "Link",
			options: "Project",
			reqd: 1,
			get_query: () => ({ filters: { project_type: "Site" } }),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			description: __("Stock counted in this warehouse and those under it; all the company's warehouses if blank"),
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "only_shortfalls",
			label: __("Only Shortfalls"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "status") {
			const colour = SMR_STATUS_COLOURS[data.status] || "gray";
			return `<span class="indicator-pill no-indicator-dot ${colour}">${value}</span>`;
		}
		if (column.fieldname === "shortfall" && flt(data.shortfall) > 0) {
			return `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
