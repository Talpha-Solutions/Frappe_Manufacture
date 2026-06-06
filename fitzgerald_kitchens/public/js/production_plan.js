// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const PROJECT_CUSTOMER_SOURCES = ["Sales Order", "Project"];

function sync_project_customer_filter(frm) {
	const show_customer = PROJECT_CUSTOMER_SOURCES.includes(frm.doc.get_items_from);
	frm.toggle_display("customer", show_customer);
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
		sync_project_customer_filter(frm);
	},

	refresh(frm) {
		sync_project_customer_filter(frm);
	},

	get_items_from(frm) {
		sync_project_customer_filter(frm);
		clear_sales_order_filters_for_project_mode(frm);
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
