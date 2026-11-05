// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Material Order Plan"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "as_on",
			label: __("As On"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: "Weekly\nBi-Weekly\nMonthly",
			default: "Weekly",
			reqd: 1,
			description: __("A column per week (from As On's Monday), fortnight, or calendar month"),
		},
		{
			fieldname: "periods",
			label: __("Number of Periods"),
			fieldtype: "Int",
			description: __("Blank: as far as the plan goes. Anything after the last period shows under Later."),
		},
		{
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: "Qty\nValue",
			default: "Qty",
			reqd: 1,
		},
		{
			fieldname: "site_project",
			label: __("Site Project"),
			fieldtype: "Link",
			options: "Project",
			description: __("All open sites if blank"),
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
			fieldname: "only_to_order",
			label: __("Only Items to Order"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const qty = flt(data[column.fieldname]);
		if (column.fieldname === "total_to_order" && qty > 0) {
			return `<span class="text-danger" style="font-weight: 600">${value}</span>`;
		}
		// period columns are p<n>_order / p<n>_consumed / p<n>_stock; p0 is Overdue
		const match = column.fieldname.match(/^p(\d+)_(order|consumed|stock)$/);
		if (!match) return value;
		if (match[2] === "order" && qty > 0) {
			const style = match[1] === "0" ? "text-danger" : "text-warning";
			return `<span class="${style}" style="font-weight: 600">${value}</span>`;
		}
		if (match[2] === "stock" && qty < 0) {
			return `<span class="text-danger">${value}</span>`;
		}
		return qty ? value : `<span class="text-muted">${value}</span>`;
	},
};
