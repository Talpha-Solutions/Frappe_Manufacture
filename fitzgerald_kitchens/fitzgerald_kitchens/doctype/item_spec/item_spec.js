// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Spec", {
	setup(frm) {
		frm.set_query("spec_list", () => ({ filters: { enabled: 1 } }));
		frm.set_query("item_code", () => ({ filters: { has_variants: 0 } }));
	},
});
