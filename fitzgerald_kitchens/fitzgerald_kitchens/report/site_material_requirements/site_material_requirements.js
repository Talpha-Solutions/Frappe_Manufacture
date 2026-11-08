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

	onload(report) {
		report.page.add_inner_button(
			__("Create Material Requests"),
			() => create_material_requests(report),
			__("Actions")
		);
	},

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

// a draft Material Issue (everything the site needs) and Purchase request (its shortfalls)
function create_material_requests(report) {
	const filters = report.get_filter_values();
	if (!filters.site_project) {
		frappe.msgprint(__("Choose a Site Project first."));
		return;
	}
	frappe.confirm(
		__(
			"Create draft Material Requests for {0}?<br><br>" +
				"<b>Material Issue</b>: everything the site needs.<br>" +
				"<b>Purchase</b>: the shortfalls.<br><br>" +
				"Quantities already on open requests for this project are left out.",
			[frappe.utils.escape_html(filters.site_project)]
		),
		() =>
			frappe.call({
				method: "fitzgerald_kitchens.fitzgerald_kitchens.report.site_material_requirements.site_material_requirements.create_material_requests",
				args: { filters },
				freeze: true,
				freeze_message: __("Creating Material Requests..."),
				callback(r) {
					const made = r.message || [];
					if (!made.length) {
						frappe.msgprint(__("Nothing to request: open Material Requests already cover this site."));
						return;
					}
					const links = made
						.map((m) => `<li>${frappe.utils.get_form_link("Material Request", m.name, true)}: ${__(m.type)}, ${__("{0} items", [m.items])}</li>`)
						.join("");
					frappe.msgprint({
						title: __("Draft Material Requests created"),
						indicator: "green",
						message: `<ul>${links}</ul>${__("Review and submit them.")}`,
					});
					report.refresh();
				},
			})
	);
}
