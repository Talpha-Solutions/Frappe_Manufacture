// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const PROJECT_CUSTOMER_SOURCES = ["Sales Order", "Project"];

function sync_project_filters(frm) {
	const is_project = frm.doc.get_items_from === "Project";
	frm.toggle_display("customer", PROJECT_CUSTOMER_SOURCES.includes(frm.doc.get_items_from));
	frm.toggle_display("fk_project_site", is_project);
}

function setup_project_site_query(frm) {
	frm.set_query("fk_project_site", () => ({
		filters: {
			company: frm.doc.company,
			project_type: "Site",
		},
	}));
}

function clear_sales_order_filters_for_project_mode(frm) {
	if (frm.doc.get_items_from !== "Project") {
		return;
	}

	// Hidden Sales Order filters can still be sent to the server and restrict results.
	const sales_order_fields = [
		"project",
		"sales_order_status",
		"from_delivery_date",
		"to_delivery_date",
	];
	for (const fieldname of sales_order_fields) {
		if (frm.doc[fieldname]) {
			frm.set_value(fieldname, null);
		}
	}
}

frappe.ui.form.on("Production Plan", {
	setup(frm) {
		setup_project_site_query(frm);
		sync_project_filters(frm);
	},

	refresh(frm) {
		setup_project_site_query(frm);
		sync_project_filters(frm);
	},

	company(frm) {
		setup_project_site_query(frm);
	},

	get_items_from(frm) {
		sync_project_filters(frm);
		clear_sales_order_filters_for_project_mode(frm);
		if (frm.doc.get_items_from !== "Project" && frm.doc.fk_project_site) {
			frm.set_value("fk_project_site", null);
		}
	},

	fk_get_projects(frm) {
		clear_sales_order_filters_for_project_mode(frm);

		frappe.call({
			method: "get_open_projects",
			doc: frm.doc,
			freeze: true,
			callback() {
				frm.refresh_field("fk_projects");
			},
		});
	},
});
