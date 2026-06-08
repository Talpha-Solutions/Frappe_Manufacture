// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Projects Settings", {
	refresh(frm) {
		frm.set_query("default_bom", "fk_capacity_pipeline_default_boms", (_doc, _cdt, cdn) => {
			const row = locals["Capacity Pipeline Default BOM"][cdn];
			return {
				filters: {
					docstatus: 1,
					is_active: 1,
					...(row?.company ? { company: row.company } : {}),
				},
			};
		});
	},
});
