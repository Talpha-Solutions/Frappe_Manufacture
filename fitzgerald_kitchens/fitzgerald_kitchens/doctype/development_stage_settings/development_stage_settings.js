frappe.ui.form.on("Development Stage Settings", {
	onload(frm) {
		load_default_stages_if_empty(frm);
	},

	refresh(frm) {
		frm.set_df_property("stages", "cannot_add_rows", false);
		frm.set_df_property("stages", "cannot_delete_rows", false);
	},
});

function load_default_stages_if_empty(frm) {
	if (frm.doc.stages && frm.doc.stages.length) {
		return;
	}

	frappe.call({
		method:
			"fitzgerald_kitchens.fitzgerald_kitchens.doctype.development_stage_settings.development_stage_settings.ensure_default_stages_for_form",
		freeze: true,
		freeze_message: __("Loading standard development stages..."),
		callback() {
			frm.reload_doc();
		},
	});
}
