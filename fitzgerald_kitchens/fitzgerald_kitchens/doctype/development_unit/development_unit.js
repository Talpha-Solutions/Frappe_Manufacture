// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Development Unit", {
	refresh(frm) {
		if (frm._loading_default_stages || (frm.doc.stages && frm.doc.stages.length)) {
			return;
		}
		load_default_stages(frm);
	},
});

function load_default_stages(frm) {
	frm._loading_default_stages = true;

	frappe.call({
		method:
			"fitzgerald_kitchens.fitzgerald_kitchens.doctype.development_unit.development_unit.get_default_stages",
		freeze: true,
		freeze_message: __("Loading standard stages..."),
		callback(r) {
			frm._loading_default_stages = false;

			if (frm.doc.stages && frm.doc.stages.length) {
				return;
			}

			if (!r.message || !r.message.length) {
				return;
			}

			r.message.forEach((row) => {
				const child = frm.add_child("stages");
				Object.assign(child, row);
			});
			frm.refresh_field("stages");
		},
	});
}
