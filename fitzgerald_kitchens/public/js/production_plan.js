// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const PROJECT_CUSTOMER_SOURCES = ["Sales Order", "Project"];

function sync_project_customer_filter(frm) {
	const show_customer = PROJECT_CUSTOMER_SOURCES.includes(frm.doc.get_items_from);
	frm.toggle_display("customer", show_customer);
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
	},

	fk_get_projects(frm) {
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
