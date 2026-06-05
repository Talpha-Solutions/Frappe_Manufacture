// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Production Plan", {
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
