// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Development Stage", {
	refresh(frm) {
		if (!frm.is_new()) return;

		frappe.set_route("Form", "Development Stage Settings");
	},
});
